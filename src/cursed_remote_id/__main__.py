#!/usr/bin/env python3
import argparse
import logging
import os
import queue
import subprocess
import sys
import threading

# Local files
import setup_logging
import aws_communicator
import channel_swapper
import csv_creator
import packet_logger


def all_requirements_installed():
    """Returns True if all required utilities are installed. Returns
    False otherwise"""

    cli_utilities = ["iw", "airmon-ng", "tshark"]
    for utility in cli_utilities:
        logger.info(f"Checking '{utility}' installation.")
        cmd = f"command -v {utility}"
        try:
            output = subprocess.check_output(
                cmd, shell=True, text=True,
            ).strip()
        except subprocess.CalledProcessError:
            logger.error(f"Could not find {utility} command-line utility.")
            return False
        logger.info(f"Found '{utility}' at '{output}'")

    # Check if Open Drone ID Wireshark dissector is installed
    logger.info("Checking Open Drone ID dissector installation.")
    # List all protocols, find lines with 'opendroneid' case-insensitive
    # Split fields by tab character (according to tshark manual page)
    # Get the third field which should be the display filter name
    # Note: tab character is inserted in by Python, so $'\t' is not needed
    cmd = "tshark -G protocols | grep -i opendroneid | cut -d '\t' -f 3"
    try:
        output = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT,
            shell=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running command {cmd}.")
        logger.error(f"STDOUT: {e.stdout}")
        return False

    critical_protocols = [
        "opendroneid",
        "opendroneid.basicid",
        "opendroneid.location",
        "opendroneid.message.pack",
    ]
    for protocol in critical_protocols:
        if protocol not in output:
            logger.error(f"Missing Open Drone ID protocol: {protocol}")
            return False
        else:
            logger.info(f"Found Open Drone ID protocol: {protocol}")

    non_critical_protocols = [
        "opendroneid.message.authentication",
        "opendroneid.message.operatorid",
        "opendroneid.message.system",
        "opendroneid.message.selfid",
    ]
    for protocol in non_critical_protocols:
        if protocol not in output:
            logger.warning(f"Missing optional protocol: {protocol}")
        else:
            logger.info(f"Found optional protocol: {protocol}")

    return True


def main():
    """Main script for setting up threads."""

    # Check if script was run with sudo/root permissions
    if os.geteuid() != 0:
        logger.warning("This script may need to be run with root permissions.")

    # Check tshark and OpenDroneID installation
    if not all_requirements_installed():
        logger.critical("Missing requirements. Exiting...")
        return 1

    # Check command-line arguments for which wireless interfaces to use
    use_wifi = not args.disable_wifi
    use_bt = not args.disable_bt

    if not use_wifi and not use_bt:
        logger.error(
            "All wireless interfaces have been disabled through "
            "command-line arguments. Cannot start scanning.",
        )
        return 1

    # Event to signal low power mode
    sleep_event = threading.Event()
    sleep_event.clear()

    # Queues to send interface names from setup thread to packet logger thread
    wifi_interface_queue = queue.Queue(maxsize=1)
    bluetooth_interface_queue = queue.Queue(maxsize=1)

    # Queue to receive channels with Remote ID packets from the packet
    # logger thread
    channel_queue = queue.Queue(maxsize=1000)

    mac_addr = "00c0cab400dd"

    channel_swapper_thread = threading.Thread(
        target=channel_swapper.main,
        args=(
            mac_addr,
            wifi_interface_queue,
            bluetooth_interface_queue,
            channel_queue,
            use_wifi,
            use_bt,
            sleep_event,
        ),
    )
    logger.info("Starting channel swapper thread...")
    channel_swapper_thread.start()

    # Queue to send packets from packet logger to csv writer thread
    packet_queue = queue.Queue(maxsize=1000)

    # Packet time out event
    pcap_timeout_event = threading.Event()
    pcap_timeout_event.clear()

    sleep_timeout = 3600  # 1 hour
    interface_setup_timeout = 5  # 30 seconds

    packet_logger_thread = threading.Thread(
        target=packet_logger.main,
        args=(
            wifi_interface_queue,
            bluetooth_interface_queue,
            packet_queue,
            use_wifi,
            use_bt,
            pcap_timeout_event,
            sleep_timeout,
            interface_setup_timeout,
        ),
    )
    logger.info("Starting packet logger thread...")
    packet_logger_thread.start()

    # Queue for indicating which files need to be uploaded to the cloud
    upload_file_queue = queue.Queue(maxsize=10)

    # Event for indicating when the csv writer thread has terminated
    csv_writer_exit_event = threading.Event()
    csv_writer_exit_event.clear()

    csv_writer_thread = threading.Thread(
        target=csv_creator.csv_writer,
        args=(
            packet_queue,
            upload_file_queue,
            csv_writer_exit_event,
        ),
    )
    logger.info("Starting csv writer thread...")
    csv_writer_thread.start()

    upload_bucket_name = "cursed-remoteid-data"
    remove_uploaded_files = False
    uploader_max_error_count = 5
    uploader_thread = threading.Thread(
        target=aws_communicator.uploader,
        args=(
            upload_file_queue,
            upload_bucket_name,
            remove_uploaded_files,
            uploader_max_error_count,
            csv_writer_exit_event,
        ),
    )
    logger.info("Starting uploader thread...")
    # uploader_thread.start()  # TODO: uncomment when ready to push to AWS

    channel_swapper_thread.join()
    packet_logger_thread.join()
    csv_writer_thread.join()
    uploader_thread.join()

    logger.info("All threads joined. Exiting...")
    return 0


if __name__ == "__main__":

    # Create command line arguments
    parser = argparse.ArgumentParser(
        description="Remote ID packet capture script.",
    )

    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--log-file", type=str, default="logs/debug.log",
        help="Log file location. Default is logs/debug.log",
    )
    parser.add_argument("--disable-wifi", action="store_true")
    parser.add_argument("--disable-bt", action="store_true")

    args = parser.parse_args()

    # Parse logging arguments
    root_logging_level = logging.INFO
    if args.verbose:
        console_logging_level = logging.INFO
    else:
        console_logging_level = logging.ERROR
    file_logging_level = logging.INFO
    if args.debug:  # debug flag takes priority over verbose flag
        root_logging_level = logging.DEBUG
        console_logging_level = logging.DEBUG
        file_logging_level = logging.DEBUG

    # Set up logging format
    setup_logging.setup_logging(
        root_level=root_logging_level,
        console_level=console_logging_level,
        file_level=file_logging_level,
        log_file=args.log_file,
    )

    # Set up main script logging
    logger = logging.getLogger(__name__)

    logger.info("Running main script.")
    sys.exit(main())
