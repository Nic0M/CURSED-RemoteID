import logging
import boto3
from botocore.exceptions import ClientError
import os
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logger.error(f"Failed to upload {file_name} to {bucket}.")
        logger.error(e)
        return False
    logger.info("SUCCESS: Uploaded file to S3 bucket successfully.")
    return True


def runner():
    file_name = "../../channelswap.sh"
    bucket_name = "cursed-remoteid-data"
    logger.info(f"Attempting to upload file {file_name} to bucket {bucket_name}.")

    start = time.time_ns()
    upload_file(file_name, bucket_name)
    end = time.time_ns()

    logger.info(f"Elapsed upload time in milliseconds {(end - start) / 1e6:.1f}")

