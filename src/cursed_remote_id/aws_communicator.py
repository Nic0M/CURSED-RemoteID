import logging
import os
import queue

# AWS modules
import boto3
import botocore.exceptions

# Local modules
import helpers

logger = logging.getLogger(__name__)


def create_s3_client():
    r"""Creates a boto3 client to communicate with Amazon Simple Storage
    Service (S3). Requires AWS config and credentials in
    the .aws folder in the home directory.
    Linux & MacOS:
        config file: ~/.aws/config
        credentials file: ~/.aws/credentials
    Windows:
        config file: %userprofile%\.aws\config
        credentials file: %userprofile%\.aws\credentials

    Example config file:
    [default]
    region = us-east-2

    Example credentials file:
    [default]
    aws_access_key_id = <key id goes here>
    aws_secret_access_key = <secret access key goes here>

    !! DO NOT COMMIT THE SECRET KEY TO GITHUB !!

    :return: S3 client object
    """
    return boto3.client("s3")


def upload_file(s3_client, file_name, bucket, object_name=None):
    r"""Upload a file to an S3 bucket. Requires AWS credentials setup. See
    create_s3_client() for details.

    :param s3_client: S3 client object

    :param file_name: Local file to upload, e.g. 'data/data1.csv'

    :param bucket: Name of S3 bucket, e.g. 'my-unique-bucket-name'

    :param object_name: What the file will be named in the S3 bucket. If the
    object name contains path separators, the file will be inserted into those
    folders in the bucket and create them if they don't already exist (e.g.
    '2024-02-29/data1.csv'). If the object name is not specified, then the
    basename of the file is used (e.g. data1.csv), and the file is uploaded to
    the root directory of the bucket.

    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    logger.info(
        f"Attempting to upload {file_name} as {object_name} to bucket "
        f"{bucket}",
    )
    try:
        s3_client.upload_file(file_name, bucket, object_name)
    except botocore.exceptions.ClientError as e:
        logger.error("Failed to upload file to bucket.")
        logger.error(e)
        return False
    logger.info("Uploaded file to bucket successfully.")
    return True


def uploader(
    file_queue, bucket_name, remove_files, max_error_count,
    csv_writer_exit_event,
):
    """Main entry point for uploader thread."""

    thread_logger = logging.getLogger("uploader-thread")
    thread_logger.setLevel(logging.INFO)

    thread_logger.info("Creating S3 client.")
    s3_client = create_s3_client()

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
            uploaded = upload_file(s3_client, file_name, bucket_name)
            if not uploaded:
                error_count += 1
                thread_logger.error(
                    f"Failed to upload file {file_name}. "
                    f"Total errors: {error_count}",
                )
            if remove_files:
                helpers.safe_remove(file_name)
        else:
            error_count += 1
            thread_logger.error(
                f"File {file_name} doesn't exist. Cannot "
                f"upload the file. Total Errors: "
                f"{error_count}.",
            )
    if error_count >= max_error_count:
        thread_logger.error(
            f"Total errors: {error_count} exceeds maximum "
            f"allowed errors: {max_error_count}.",
        )
    thread_logger.info("Terminating thread.")
    return None
