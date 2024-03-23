import csv
import logging
import os
import queue
import re
import time
import uuid
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

# Local files
import helpers

logger = logging.getLogger(__name__)


def clean_tmp_csv_directory():
    os_name = os.name
    match os_name:
        case "posix":
            tmp_directory = PurePosixPath("/var", "tmp")
        case "nt":
            tmp_directory = PureWindowsPath(
                "C:", "Users", "AppData", "Local",
                "Temp",
            )
        case _:
            logger.error(
                f"Unknown OS {os_name}. Using current directory to "
                f"store temporary files.",
            )
            tmp_directory = ""
    tmp_directory = Path(tmp_directory, "remote-id-data")
    logger.info(f"Storing temporary files in {tmp_directory}")
    try:
        tmp_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        logger.info("Directory already exists, deleting existing files.")
        # If the folder exists, there may be leftover files from a previous run
        for (dir_name, _, base_names) in os.walk(
            tmp_directory,
            followlinks=False,
        ):
            # Delete all files in the tmp directory
            for base_name in base_names:
                helpers.safe_remove(PurePath(dir_name, base_name))
            break  # Don't recursively walk through directories
    return tmp_directory


header_row = [
    "Source Address", "Unique ID", "Timestamp", "Heading",
    "Ground Speed", "Vertical Speed", "Latitude", "Longitude",
]


class InvalidRemoteIDPacketError(Exception):
    """Packet does not use the Open Drone ID protocol."""


class MissingSourceAddressError(InvalidRemoteIDPacketError):
    """Packet is missing the source address."""


class MissingRemoteIDInformationError(InvalidRemoteIDPacketError):
    """Packet is missing Remote ID information."""


class MissingUniqueIDError(InvalidRemoteIDPacketError):
    """Packet is missing Unique ID found in the Open Drone ID
    (Basic ID message)."""


class MissingTimestampError(InvalidRemoteIDPacketError):
    """Packet is missing a UTC timestamp or the timestamp since the UTC hour
    in the Open Drone ID (Location Message)"""


def create_row(pkt):
    """Creates a table of elements corresponding to one row of the CSV."""
    # Determine if Bluetooth or Wi-Fi packet
    try:
        src_addr = pkt.btle.advertising_address
    except AttributeError:
        try:
            src_addr = pkt.wlan.sa_resolved
        except AttributeError:
            raise MissingSourceAddressError

    # Get Open Drone ID information
    try:
        opendroneid_data = pkt.opendroneid
    except AttributeError:
        raise MissingRemoteIDInformationError

    # Unique ID
    try:
        unique_id = opendroneid_data.opendroneid_basicid_id_asc
    except AttributeError:
        raise MissingUniqueIDError
    unique_id = str(unique_id)
    # Remove non-word characters (everything that is not a letter, underscore,
    # number or dash)
    unique_id = re.sub(r"[^\w-]+", "", unique_id)
    # ASTM F3411-22a Basic ID numbers should be 20 characters or less
    if len(unique_id) > 20:
        unique_id = unique_id[0:20]

    # Timestamp
    try:
        epoch_timestamp = pkt.frame_info.time_epoch
        time_since_utc_hour = opendroneid_data.opendroneid_loc_timestamp
    except AttributeError:
        raise MissingTimestampError
    epoch_timestamp = float(epoch_timestamp)
    remoteid_utc_timestamp = epoch_timestamp - (epoch_timestamp % 3600) \
        + int(time_since_utc_hour) // 10
    timestamp = time.strftime(
        '%Y-%m-%d %H:%M:%S',
        time.gmtime(remoteid_utc_timestamp),
    )

    # Other
    try:
        heading = opendroneid_data.opendroneid_loc_direction
        gnd_speed = opendroneid_data.opendroneid_loc_speed
        vert_speed = opendroneid_data.opendroneid_loc_vspeed
        lat = opendroneid_data.opendroneid_loc_lat
        lon = opendroneid_data.opendroneid_loc_lon
    except AttributeError:
        raise InvalidRemoteIDPacketError

    # if lat <= 0 and lon == 0:
    #     raise InvalidRemoteIDPacketError

    row = [
        src_addr, unique_id, timestamp, heading, gnd_speed, vert_speed,
        lat, lon,
    ]
    return row


def csv_writer(
    packet_queue, upload_file_queue, exit_event,
    max_packet_count=100,
    max_elapsed_time=300,  # 5 minutes
    max_error_count=10,
    upload_file_queue_timeout=5,  # 5 seconds
):
    """Main entry point for CSV writer thread."""

    logger.info("Cleaning .csv file temporary directory.")
    tmp_directory = clean_tmp_csv_directory()

    error_count = 0
    # while error_count < max_error_count: # TODO: implement
    if True:

        # Create a new .csv file with a unique hash for the filename
        base_name = "remote-id-" + str(uuid.uuid4()) + ".csv"
        file_name = PurePath(tmp_directory, base_name)

        packet_count = 0

        # 'w' creates the file if it doesn't already exist and overwrites any
        # existing data if the file already exists
        with open(file_name, 'w', newline='', encoding="utf-8") as csv_file:
            logger.info(f"Opened file {file_name}")
            writer = csv.writer(csv_file)

            writer.writerow(header_row)

            current_time = time.monotonic()
            elapsed_time = 0

            while packet_count <= max_packet_count \
                    and elapsed_time < max_elapsed_time:

                try:
                    packet = packet_queue.get(
                        timeout=5,
                    )  # Blocks until next packet is received
                except queue.Empty:
                    logger.info("Timed out waiting for packet queue.")
                    break

                if packet is None:
                    logger.info(
                        "Received termination message from packet "
                        "queue.",
                    )
                    break

                try:
                    row = create_row(packet)
                except InvalidRemoteIDPacketError as e:
                    logger.error(f"Error parsing packet: {repr(e)}")
                    continue
                writer.writerow(row)

                packet_count += 1
                elapsed_time = time.monotonic() - current_time

            logger.info(f"Closing file with {packet_count} packets.")

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
                helpers.safe_remove(file_name)
        else:
            logger.info("Removing file with no packets.")
            helpers.safe_remove(file_name)

    if error_count >= max_error_count:
        logger.error(
            f"Total errors: {error_count} exceeds the maximum "
            f"allowable errors: {max_error_count}.",
        )

    logger.info("Terminating thread.")

    # Exit event is set before adding None element to queue to guarantee the
    # uploader will not block indefinitely on an empty queue
    exit_event.set()
    upload_file_queue.put(None)
