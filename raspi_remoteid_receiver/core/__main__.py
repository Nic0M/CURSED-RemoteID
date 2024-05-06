import argparse
import logging.handlers
import multiprocessing
import os
import queue
import signal
import subprocess
import sys
import threading

# Local files
from raspi_remoteid_receiver.core import setup_logging, aws_communicator, channel_swapper, csv_creator, packet_logger


def all_requirements_installed() -> bool:
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
            error_msg = f"Could not find '{utility}' command-line utility."
            match utility:
                case "iw":
                    help_msg = "Try 'sudo apt install iw'."
                case "airmon-ng":
                    help_msg = "Try 'sudo apt install aircrack-ng'."
                case "tshark":
                    help_msg = (
                        "Try 'sudo apt install tshark'. "
                        "If Wireshark is already installed, try adding the"
                        "tshark binary executable to PATH."
                    )
                case _:
                    help_msg = ""
            logger.error(f"{error_msg} {help_msg}")
            return False
        logger.info(f"Found '{utility}' at '{output}'")

    # TODO: add lua script from repo if not installed
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
        "opendroneid.message.basicid",
        "opendroneid.message.location",
        "opendroneid.message.pack",
    ]
    for protocol in critical_protocols:
        if protocol not in output:
            logger.error(f"Missing Open Drone ID protocol: {protocol}")
            return False
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


def main() -> int:
    """Main script for setting up threads."""

    # Check if script was run with sudo/root permissions
    if os.geteuid() != 0:
        logger.warning("This script may need to be run with root permissions.")

    # Check tshark and OpenDroneID installation
    if not args.no_check_requirements and not all_requirements_installed():
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
    sleep_event = multiprocessing.Event()
    # KeyboardInterrupt event (SIGINT)
    keyboard_interrupt_event = threading.Event()

    # Queues to send interface names from setup thread to packet logger thread
    wifi_interface_queue = multiprocessing.Queue(maxsize=1)
    bluetooth_interface_queue = multiprocessing.Queue(maxsize=1)

    # Queue to receive channels with Remote ID packets from the packet
    # logger thread
    channel_queue = queue.Queue(maxsize=1000)

    channel_swapper_thread = threading.Thread(
        target=channel_swapper.main,
        args=(
            wifi_interface_queue,
            bluetooth_interface_queue,
            channel_queue,
            use_wifi,
            use_bt,
            sleep_event,
            keyboard_interrupt_event,
            log_queue,
        ),
    )
    logger.info("Starting channel swapper thread...")
    channel_swapper_thread.start()

    # Queue to send packets from packet logger to csv writer thread
    packet_queue = multiprocessing.Queue(maxsize=1000)

    # Packet time out event
    pcap_timeout_event = multiprocessing.Event()

    sleep_timeout = 3600  # 1 hour
    interface_setup_timeout = 30  # 30 seconds

    packet_logger_process = packet_logger.PacketLoggerProcess(
        wifi_interface_queue=wifi_interface_queue,
        bt_interface_queue=bluetooth_interface_queue,
        packet_queue=packet_queue,
        log_queue=log_queue,
        logging_level=root_logging_level,
        use_wifi=use_wifi,
        use_bt=use_bt,
        pcap_timeout_event=pcap_timeout_event,
        sleep_event=sleep_event,
        sleep_timeout=sleep_timeout,
        interface_timeout=interface_setup_timeout,
    )
    logger.info("Starting packet logger process")
    packet_logger_process.start()

    # Queue for indicating which files need to be uploaded to the cloud
    upload_file_queue = queue.Queue(maxsize=10)

    # Event for indicating when the csv writer thread has terminated
    csv_writer_exit_event = threading.Event()
    csv_writer_exit_event.clear()

    csv_writer_thread = csv_creator.CSVCreatorThread(
        packet_queue=packet_queue,
        log_queue=log_queue,
        upload_file_queue=upload_file_queue,
        exit_event=csv_writer_exit_event,
        sleep_event=sleep_event,
        sigint_event=keyboard_interrupt_event,
    )

    upload_bucket_name = args.bucket_name
    uploader_max_error_count = 5
    uploader_thread = threading.Thread(
        target=aws_communicator.uploader,
        args=(
            upload_file_queue,
            upload_bucket_name,
            uploader_max_error_count,
            csv_writer_exit_event,
            keyboard_interrupt_event,
            log_queue,
        ),
    )

    logger.info("Starting csv writer thread...")
    csv_writer_thread.start()
    if args.upload_to_aws:
        logger.info("Starting uploader thread...")
        uploader_thread.start()
    else:
        logger.warning("Skipping upload. Set --upload-to-aws to enable upload")

    # TODO: sleep event

    first_sigint = True

    def sigint_handler(sig: int, frame) -> None:
        if sig == signal.SIGINT:
            nonlocal first_sigint
            if not first_sigint:
                # Kill all processes with no cleanup
                packet_logger_process.kill()
                os._exit(1)
            # Send SIGINT signal is automatically sent to all processes
            print(
                "\nCaught SIGINT, closing threads...",
                file=sys.stderr, flush=True,
            )
            keyboard_interrupt_event.set()
            # Unblock channel swapper thread
            try:
                wifi_interface_queue.put_nowait(None)
            except queue.Full:
                pass
            try:
                bluetooth_interface_queue.put_nowait(None)
            except queue.Full:
                pass
            # Unblock packet logger thread
            try:
                packet_queue.put_nowait(None)
            except queue.Full:
                pass
            # Unblock csv writer thread
            try:
                packet_queue.put_nowait(None)
            except queue.Full:
                pass
            # Unblock uploader thread
            try:
                upload_file_queue.put_nowait(None)
            except queue.Full:
                pass
            first_sigint = False

    signal.signal(signal.SIGINT, sigint_handler)

    channel_swapper_thread.join()
    packet_logger_process.join()
    csv_writer_thread.join()

    if args.upload_to_aws:
        uploader_thread.join()

    logger.info("All non-daemon threads joined. Exiting...")
    return 0


if __name__ == "__main__":
    # if this is "fork", then all processes need to be started before any
    # threads are started
    multiprocessing.set_start_method("spawn")

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
    parser.add_argument(
        "--upload-to-aws", action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--bucket-name", type=str, default="cursed-remoteid-data",
        help="Amazon S3 bucket name. Default is 'cursed-remoteid-data'",
    )
    parser.add_argument(
        "--no-check-requirements", action="store_true",
    )
    parser.add_argument(
        "--tshark-capture",
        type=int,
        default=-
        1,
        help="use custom tshark capture with interface number from output of tshark -D",
    )

    args = parser.parse_args()

    # Parse logging arguments
    root_logging_level = logging.INFO
    if args.verbose:
        console_logging_level = logging.INFO
    else:
        console_logging_level = logging.WARNING
    file_logging_level = logging.INFO
    if args.debug:  # debug flag takes priority over verbose flag
        root_logging_level = logging.DEBUG
        console_logging_level = logging.DEBUG
        file_logging_level = logging.DEBUG

    log_queue = multiprocessing.Queue()

    # Set up logging format
    queue_listener = setup_logging.setup_logging(
        log_queue=log_queue,
        root_level=root_logging_level,
        console_level=console_logging_level,
        file_level=file_logging_level,
        log_file=args.log_file,
    )
    queue_listener.start()

    # Set up main script logging
    logger = setup_logging.get_logger(__name__, log_queue)

    logger.info("Running main script.")

    exit_code = main()

    # Stop the queue listener
    queue_listener.stop()

    sys.exit(exit_code)
