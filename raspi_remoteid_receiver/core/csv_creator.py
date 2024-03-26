import csv
import logging
import os
import queue
import re
import threading
import time
import uuid
import pathlib

# Local files
from raspi_remoteid_receiver.core import helpers

logger = logging.getLogger(__name__)


def clean_tmp_csv_directory() -> pathlib.Path:
    """Chooses a temporary directory to store CSV files. If the directory
    already exists, removes any existing old CSV files from previous runs.
    Returns the file path of the temporary directory.
    """
    os_name = os.name
    match os_name:
        case "posix":
            tmp_directory = pathlib.PurePosixPath("/var", "tmp")
        case "nt":
            tmp_directory = pathlib.PureWindowsPath(
                "C:", "Users", "AppData", "Local",
                "Temp",
            )
        case _:
            logger.error(
                f"Unknown OS {os_name}. Using current directory to "
                f"store temporary files.",
            )
            tmp_directory = "tmp"
    tmp_directory = pathlib.Path(tmp_directory, "remote-id-data")
    logger.info(f"Storing temporary files in {tmp_directory}")
    try:
        tmp_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        logger.info("Directory already exists, deleting existing files.")
        # If the folder exists, there may be leftover files from a previous run
        for (dir_name, _, base_names) in os.walk(
            tmp_directory,
            followlinks=False,  # don't follow symlinks
        ):
            # Delete all files in the tmp directory
            for base_name in base_names:
                file_path = pathlib.PurePath(dir_name, base_name)
                logger.info(f"Removing file: '{file_path}'")
                helpers.safe_remove_csv(file_path)
            break  # Don't recursively walk through directories
    return tmp_directory


header_row = [
    "Source Address", "Unique ID", "Timestamp", "Heading",
    "Ground Speed", "Vertical Speed", "Latitude", "Longitude",
    "Geodetic Altitude", "Speed Accuracy", "Horizontal Accuracy",
    "Geodetic Vertical Accuracy", "Barometric Altitude",
    "Barometric Altitude Accuracy", "Height", "Height Type",
]


class PacketError(Exception):
    """Packet does not use the Open Drone ID protocol or is invalid."""


class MissingPacketFieldError(PacketError):
    """Packet is missing a required field."""


class InvalidPacketFieldError(PacketError):
    """Packet is missing a required field."""


def is_valid_src_addr(src_addr: str) -> bool:
    """Returns True if a valid source address string. Returns False otherwise.
    Valid source addresses are MAC addresses or Bluetooth Device Addresses.
    There should be a prefix of either 'MAC-' or 'BDA-' followed by
    12 upper case hexadecimal characters, separated by a colon every 2 digits.

    **** INPUT MUST BE UPPER CASE ****
    Valid:
        MAC-FF:FF:FF:FF:FF:FF
        BDA-00:11:22:33:44:55
    Invalid:
        MAC-ff:ff:ff:ff:ff:ff
        bda-00:11:22:33:44:55
    """
    if src_addr is None:
        return False
    match = re.match(
        r'\A(?:MAC|BDA)-(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z', src_addr,
    )
    return match is not None


def create_row(pkt) -> list:
    """Creates a table of elements corresponding to one row of the CSV.
    It looks like PyShark generates the format of the packet by taking the
    display filter for that field from Wireshark and replacing all periods
    with underscores, case-insensitive.
    This filter can be found by right-clicking on the desired field and
    selecting Copy > Field Name
    The field names appear to be generated somehow from the .lua script names,
    but I can't figure out how it works—the names don't seem to exactly match.
    Ex:
        OpenDroneID.loc_geoAlt --> opendroneid_loc_geoalt
        opendroneid.message.operatorid --> opendroneid_message_operatorid

    """

    # Determine if Bluetooth or Wi-Fi packet
    try:
        # TODO: see if this works for Bluetooth 4 legacy packets
        src_addr = pkt.btle.advertising_address
    except AttributeError:
        try:
            src_addr = pkt.wlan.sa_resolved
        except AttributeError:
            logger.info("Missing Source Address")
            raise MissingPacketFieldError("Missing Source Address")
        src_addr = "MAC-" + src_addr
    else:
        src_addr = "BDA-" + src_addr
    src_addr = src_addr.upper()
    if not is_valid_src_addr(src_addr):
        logger.info(f"Invalid Source Address {src_addr}")
        raise InvalidPacketFieldError(f"Invalid Source Address: {src_addr}")

    # Get Open Drone ID information
    try:
        opendroneid_data = pkt.opendroneid
    except AttributeError:
        logger.info("Open Drone ID Data")
        raise MissingPacketFieldError("Missing Open Drone ID Protocol")

    # Unique ID
    try:
        unique_id = opendroneid_data.opendroneid_basicid_id_asc
    except AttributeError:
        raise MissingPacketFieldError("Missing Unique ID")
    # Remove non-alphanumeric characters and strip whitespace
    unique_id = str(unique_id)
    unique_id = re.sub(r"[^0-9a-zA-Z_\- ]+", "", unique_id).strip()
    # ASTM F3411-22a Basic ID numbers should be max 20 characters
    if len(unique_id) > 20:
        logger.info(f"Invalid Unique ID: {unique_id}")
        raise InvalidPacketFieldError(f"Invalid Unique ID: {unique_id}")

    # Timestamp
    try:
        epoch_timestamp = pkt.frame_info.time_epoch
    except AttributeError:
        logger.info("Missing Epoch Time")
        raise MissingPacketFieldError("Missing Epoch Timestamp")
    try:
        # This value is in tenths of seconds
        # Ex: 3611 corresponds to 6 minutes 1.1 seconds
        time_since_utc_hour = opendroneid_data.opendroneid_loc_timestamp
    except AttributeError:
        logger.info("Missing UTC Time Since Hour")
        raise MissingPacketFieldError("Missing Location Message Timestamp")
    epoch_timestamp = float(epoch_timestamp)
    time_since_utc_hour = int(time_since_utc_hour) % 3600
    remote_id_utc_timestamp = epoch_timestamp - (epoch_timestamp % 3600) \
        + time_since_utc_hour // 10
    # Check if drone is time traveling to the future
    # (usually happens when no GPS lock)
    now = round(time.time())  # number of seconds since epoch
    remote_id_utc_timestamp = min(remote_id_utc_timestamp, now)
    timestamp = time.strftime(
        '%Y-%m-%d %H:%M:%S',
        time.gmtime(remote_id_utc_timestamp),
    )
    timestamp += "." + str(time_since_utc_hour % 10)

    # Other
    try:
        heading = opendroneid_data.opendroneid_loc_direction
        gnd_speed = opendroneid_data.opendroneid_loc_speed
        vert_speed = opendroneid_data.opendroneid_loc_vspeed
        lat = opendroneid_data.opendroneid_loc_lat
        lon = opendroneid_data.opendroneid_loc_lon
    except AttributeError:
        raise MissingPacketFieldError("Something in location message")

    # Geodetic Altitude
    try:
        geo_alt = opendroneid_data.opendroneid_loc_geoalt
    except AttributeError:
        raise MissingPacketFieldError("Missing Geodetic Altitude")
    else:
        # Value should be an int
        geo_alt = int(geo_alt)

    # Geodetic Vertical Accuracy
    try:
        geo_vert_acc = opendroneid_data.opendroneid_loc_vaccuracy
    except AttributeError:
        raise MissingPacketFieldError("Missing Geodetic Vertical Accuracy")
    else:
        # Value should be an int between 0 and 15
        geo_vert_acc = int(geo_vert_acc)  # can raise ValueError or TypeError
        if not 0 <= geo_vert_acc <= 15:
            # TODO: maybe set to 0 (equivalent to '>= 10m/s' or 'unknown')
            #  instead of raising error
            raise InvalidPacketFieldError("Geodetic Vertical Accuracy")

    # Speed Accuracy
    try:
        speed_acc = opendroneid_data.opendroneid_loc_speedaccuracy
    except AttributeError:
        raise MissingPacketFieldError("Missing Speed Accuracy")
    else:
        speed_acc = int(speed_acc)
        if speed_acc > 15:
            logger.warning("Invalid speed accuracy. Setting to unknown.")
            speed_acc = 0
        if speed_acc > 4:
            logger.warning("Reserved speed accuracy in ASTM F3411-22a.")
        if speed_acc < 0:
            logger.warning(
                "Negative speed accuracy. Possible conversion"
                "error from unsigned int to signed int.",
            )
            speed_acc = 0

    # Horizontal Accuracy
    try:
        horz_acc = opendroneid_data.opendroneid_loc_haccuracy
    except AttributeError:
        raise MissingPacketFieldError("Missing Horizontal Accuracy")
    else:
        horz_acc = int(horz_acc)
        if not 0 <= horz_acc <= 15:
            logger.warning("Invalid horizontal accuracy. Setting to unknown.")
            horz_acc = 0

    # Barometric Altitude (optional in ASTM F3411-22a)
    try:
        baro_alt = opendroneid_data.opendroneid_loc_pressalt  # pressure alt
    except AttributeError:
        # If Invalid, No Value, or Unknown => -1000 m
        baro_alt = -1000
    else:
        baro_alt = int(baro_alt)
        if baro_alt > 31767:  # 31767 is max 16-bit signed int 32767 - 1000
            # This should not be possible
            logger.warning("Invalid barometric altitude, exceeds int16 value.")
            baro_alt = -1000
        else:
            # TODO: conversion in standard, based on observation, some drones
            #  may not be compliant
            baro_alt = (baro_alt + 1000) / 2

    try:
        baro_alt_acc = opendroneid_data.opendroneid_loc_baroaccuracy
    except AttributeError:
        # Is optional
        baro_alt_acc = 0
    else:
        baro_alt_acc = int(baro_alt_acc)
        # TODO: Check if baro accuracy is also int16 in ASTM F3411-22a
        if not 0 <= baro_alt_acc <= 15:
            baro_alt_acc = 0

    try:
        height = opendroneid_data.opendroneid_loc_height
    except AttributeError:
        # Field is optional, don't throw error if missing
        height = -1000
    else:
        height = int(height)
        if not -1000 <= height <= 31767:  # see altitudes
            height = -1000
        else:
            height = (height + 1000) / 2

    try:
        height_type = opendroneid_data.opendroneid_loc_flag_heighttype
    except AttributeError:
        # Field is optional, don't throw error if missing
        height_type = 0
    else:
        if height_type not in (0, 1):
            height_type = 0

    row = [
        src_addr, unique_id, timestamp, heading, gnd_speed, vert_speed,
        lat, lon, geo_alt, speed_acc, horz_acc, geo_vert_acc, baro_alt,
        baro_alt_acc, height, height_type,
    ]
    return row


def main(
    packet_queue: queue.Queue, upload_file_queue: queue.Queue,
    exit_event: threading.Event, sleep_event: threading.Event,
    sigint_event: threading.Event,
    max_packet_count=100,
    max_elapsed_time=300,  # 5 minutes
    upload_file_queue_timeout=5,  # 5 seconds
    packet_timeout=120,  # 2 minutes of no Open Drone ID packets
) -> int:
    """Main entry point for CSV writer thread."""

    tmp_directory = clean_tmp_csv_directory()  # Housekeeping

    go_again = True
    while go_again:

        if sleep_event.is_set():
            break

        # Create a new .csv file with a unique hash for the filename
        base_name = "remote-id-" + str(uuid.uuid4()) + ".csv"
        file_name = pathlib.PurePath(tmp_directory, base_name)

        packet_count = 0  # number of packets in the current csv file

        # 'w' creates the file if it doesn't already exist and overwrites any
        # existing data if the file already exists (which it shouldn't)
        with open(file_name, 'w', newline='', encoding="utf-8") as csv_file:
            logger.info(f"Opened file {file_name}")
            writer = csv.writer(csv_file)

            writer.writerow(header_row)

            current_time = time.monotonic()
            elapsed_time = 0

            while packet_count <= max_packet_count \
                    and elapsed_time < max_elapsed_time:
                # Detected KeyboardInterrupt in main thread
                if sigint_event.is_set():
                    break
                try:
                    packet = packet_queue.get(
                        timeout=packet_timeout,
                    )  # Blocks until next packet is received
                except queue.Empty:
                    logger.info("Timed out waiting for packet queue.")
                    go_again = False
                    break

                if packet is None:
                    logger.info(
                        "Received termination message from packet queue.",
                    )
                    go_again = False
                    break

                try:
                    row = create_row(packet)
                except PacketError as e:
                    logger.error(f"Error parsing packet: {repr(e)}")
                    continue
                except TypeError as e:
                    logger.error(f"TypeError when parsing packet: {repr(e)}")
                    continue
                writer.writerow(row)

                packet_count += 1
                elapsed_time = time.monotonic() - current_time

            logger.info(f"Closing file with {packet_count} packets.")

        if sigint_event.is_set():
            logger.info(f"Detected SIGINT event. Deleting {file_name}")
            helpers.safe_remove_csv(file_name)
            logger.info("Exiting thread...")
            return 0

        # Send file to be uploaded if not empty.
        if packet_count > 0:
            try:
                upload_file_queue.put(
                    file_name, block=True,
                    timeout=upload_file_queue_timeout,
                )
            except queue.Full:
                logger.error(
                    f"Upload file queue is full, skipping "
                    f"file {file_name}.",
                )
                helpers.safe_remove_csv(file_name)
        else:
            logger.info("Removing file with no packets.")
            helpers.safe_remove_csv(file_name)

    logger.info("Exiting thread...")

    # Exit event is set before adding None element to queue to guarantee the
    # uploader will not block indefinitely on an empty queue
    exit_event.set()
    upload_file_queue.put(None)

    return 0
