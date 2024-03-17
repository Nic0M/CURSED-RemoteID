import logging
from pathlib import Path
import threading
import queue
import os
import pyshark
import subprocess

# Local files
import setup_logging
import aws_communicator
import csv_creator
import helpers


def packet_logger():

    interface_name = "wlan1mon"
    interface_name = "wlan1"

    # Gets a list of supported channels separated by new lines
    get_channels_cmd = f"iw phy {interface_name} channels 2>&1" + \
                       r" | awk -F'[][]' '$2{print $2}'"
    logger.debug(f"Running command: {get_channels_cmd}")
    output = subprocess.check_output(get_channels_cmd, shell=True, text=True)
    supported_channels = output.strip().split('\n')

    channel = supported_channels[0]

    set_channel_cmd = f"iw dev {interface_name} set channel {channel} 2>&1"
    logger.debug(f"Running command: {set_channel_cmd}")
    output = subprocess.check_output(set_channel_cmd, shell=True, text=True)
    if output != "":
        logger.error(f"Failed to switch to channel {channel}.")
        if "(-16)" in output:
            logger.error(f"Interface {interface_name} is likely no longer in "
                         f"monitor mode.")
        if "(-22)" in output:
            logger.error(f"Channel {channel} cannot be legally used.")
        logger.error(output)
    else:
        logger.info(f"Switched to channel {channel} successfully.")


def uploader(file_queue, bucket_name, remove_files, max_error_count,
             csv_writer_exit_event):
    thread_logger = logging.getLogger("uploader-thread")
    thread_logger.setLevel(logging.INFO)

    thread_logger.info("Creating S3 client.")
    s3_client = aws_communicator.create_s3_client()

    error_count = 0
    while error_count < max_error_count:
        # Only block if the csv_writer thread hasn't terminated
        if not csv_writer_exit_event.is_set():
            file_name = file_queue.get()  # Blocks if the queue is empty
        else:
            try:
                file_name = file_queue.get(block=False)
            except queue.Empty:
                thread_logger.info("Queue is empty and csv_writer has exited")
                break

        if file_name is None:
            thread_logger.info("Received termination message from queue.")
            break
        if os.path.exists(file_name):
            uploaded = aws_communicator.upload_file(s3_client, file_name,
                                                    bucket_name)
            if not uploaded:
                error_count += 1
                thread_logger.error(f"Failed to upload file {file_name}. "
                                    f"Total errors: {error_count}")
            if remove_files:
                helpers.safe_remove(file_name)
        else:
            error_count += 1
            thread_logger.error(f"File {file_name} doesn't exist. Cannot "
                                f"upload the file. Total Errors: "
                                f"{error_count}.")
    if error_count >= max_error_count:
        thread_logger.error(f"Total errors: {error_count} exceeds maximum "
                            f"allowed errors: {max_error_count}.")
    thread_logger.info("Terminating thread.")
    return


def main():
    setup_logging.logging_test()

    path = "/Users/ocin/Downloads/bluetoothwifiTest.pcapng"
    pcap = pyshark.FileCapture(path,
                               display_filter="opendroneid.message.location")

    packet_queue = queue.Queue(maxsize=1000)
    for pkt in pcap:
        try:
            packet_queue.put(pkt, block=False)
        except queue.Full:
            break
    try:
        packet_queue.put(None, block=False)
    except queue.Full:
        pass

    upload_file_queue = queue.Queue(maxsize=10)

    csv_writer_exit_event = threading.Event()
    csv_writer_exit_event.clear()  # May not be necessary if cleared by default
    remove_files = False
    csv_writer_thread = threading.Thread(target=csv_creator.csv_writer,
                                         args=(packet_queue,
                                               upload_file_queue,
                                               csv_writer_exit_event,
                                               remove_files)
                                         )

    # upload_file_queue.put("../../channelswap.sh")
    # upload_file_queue.put(None)

    upload_bucket_name = "cursed-remoteid-data"
    remove_uploaded_files = False
    uploader_max_error_count = 5
    uploader_thread = threading.Thread(target=uploader,
                                       args=(upload_file_queue,
                                             upload_bucket_name,
                                             remove_uploaded_files,
                                             uploader_max_error_count,
                                             csv_writer_exit_event)
                                       )

    csv_writer_thread.start()
    uploader_thread.start()

    csv_writer_thread.join()
    uploader_thread.join()
    return 0


if __name__ == "__main__":

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    logger.info("Running main script.")
    main()
