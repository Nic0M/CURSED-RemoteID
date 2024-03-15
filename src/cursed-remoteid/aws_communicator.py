import logging
import boto3
from botocore.exceptions import ClientError
import os
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
    r"""Upload a file to an S3 bucket. Requires AWS

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

    logger.info(f"Attempting to upload {file_name} as {object_name} to bucket "
                f"{bucket}")
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logger.error(f"Failed to upload file to bucket.")
        logger.error(e)
        return False
    logger.info(f"Uploaded file to bucket successfully.")
    return True


def runner():
    file_name = "../../channelswap.sh"
    bucket_name = "cursed-remoteid-data"
    logger.info(f"Attempting to upload file {file_name} to bucket {bucket_name}.")

    s3_client = create_s3_client()
    start = time.time_ns()
    upload_file(s3_client, file_name, bucket_name)
    end = time.time_ns()

    logger.info(f"Elapsed upload time in milliseconds {(end - start) / 1e6:.1f}")

