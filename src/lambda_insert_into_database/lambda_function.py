import json
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import logging
import os
import sys
import pymysql

# Set logging levels
logger = logging.getLogger()
logger.setLevel(
    logging.DEBUG)  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL


def get_database_credentials():
    """Reads the Lambda environment variables to get the RDS database
    credentials.
    """

    try:
        user = os.environ["DB_USER_NAME"]
        pwd = os.environ["DB_PASSWORD"]
        host = os.environ["RDS_HOST"]
        db = os.environ["DB_NAME"]
    except KeyError as e:
        logger.error(
            f"ERROR: Could not retrieve database credentials from environment variables. {repr(e):s}.")
        return (None, None, None, None)

    logger.info(
        "SUCCESS: Found database credentials in environment variables.")
    return (user, pwd, host, db)


# Get database credentials
user_name, password, rds_proxy_host, db_name = get_database_credentials()


def connect_to_database(user, pwd, host, db):
    """Attempts to connects to RDS database. Returns the connection object if
    succesful. Returns None if unsuccessful"""

    # logging.debug("DEBUG: Skipping database connection attempt.")
    # return None

    try:
        connection = pymysql.connect(host=host, user=user, passwd=pwd, db=db,
                                     connect_timeout=5)
    except pymysql.MySQLError as e:
        logger.error(
            "ERROR: Unexpected error: Could not connect to MySQL instance.")
        logger.error(e)
        return None

    logger.info("SUCCESS: Connection to RDS for MySQL instance succeeded.")
    return connection


# Connect to database
if user_name is not None:
    logger.debug("DEBUG: user_name is not None")
    conn = connect_to_database(user_name, password, rds_proxy_host, db_name)
else:
    conn = None


def create_s3_client():
    logger.info("Attempting to create a boto3 S3 client.")
    try:
        s3_client = boto3.client("s3")
    except Exception as e:
        logger.error("ERROR: Failed to create a boto3 S3 client.")
        logger.error(e)
        return None

    logger.info("SUCCESS: Created boto3 S3 client.")
    return s3_client


# logger.debug("DEBUG: Skipping creating s3 client.")
logger.info("Creating S3 boto client.")
s3 = create_s3_client()


def lambda_handler(event, context):
    """This function reads data from an S3 bucket and writes the data to the
    database.
    """
    global conn  # this variable can get updated in the lambda_handler function
    global s3

    logging.info("Received event: " + json.dumps(event, indent=2))

    if user_name is None:
        return 502

    if conn is None or not conn.open:
        logger.warning(
            "WARNING: Database connection doesn't exist. Attempting to reconnect to database.")
        conn = connect_to_database(user_name, password, rds_proxy_host,
                                   db_name)
        if conn is None:
            logger.error("ERROR: Couldn't reconnect to database.")
            return 502
        else:
            logger.info("SUCCESS: Reconnected to database successfully.")

    if s3 is None:
        logger.warning(
            "WARNING: s3 boto3 client doesn't exist. Attempting to recreate client.")
        s3 = create_s3_client()
        if s3 is None:
            logger.error("ERROR: Failed to recreate s3 client.")
            return 502
        else:
            logger.info("SUCCESS: Recreated s3 client successfully.")

    # logger.debug("DEBUG: Skipping s3 bucket extraction.")
    logger.info("Extracting bucket info from event record.")
    try:
        # Get the object from the event and show its content type
        bucket = event['Records'][0]['s3']['bucket']['name']
        # Get the filename
        key = urllib.parse.unquote_plus(
            event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    except KeyError as e:
        logger.error(
            "ERROR: Invalid record in event. Make sure the lambda_handler is triggered from an S3 upload.")
        logger.error(e)
    logger.info("SUCCESS: Parsed record in event successfully.")

    logger.info(f"Attempting to get object {key} from bucket {bucket}.")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        logger.error(
            f"ERROR: Failed to get object {key} from bucket {bucket}. Make sure they exist and your bucket is in the same region as this function.")
        logger.error(e)
        return {
            "StatusCode": 502,
            "Body": "Failed to get object from bucket."
        }
    logger.info("SUCCESS: Retrieved object successfully.")
    logger.info(f"CONTENT TYPE: {response['ContentType']}")

    try:
        file_reader = response['Body'].read().decode("utf-8")
    except Exception as e:
        logger.error("Error decoding file")
        logger.error(e)

    rows = file_reader.split("\n")
    rows = list(filter(None, rows))
    packets = []
    first_row = True
    for row in rows:
        if first_row:
            first_row = False
            continue
        user_data = row.replace('\r', '').split(",")
        logger.info(f"Creating packet from data: {user_data}")
        src_addr = user_data[0]
        id = user_data[1]
        timestamp = user_data[2]
        heading = int(user_data[3])
        ground_speed = int(user_data[4])
        vertical_speed = int(user_data[5])
        lat = int(user_data[6])
        lon = int(user_data[7])

        packet = (
        src_addr, id, timestamp, heading, ground_speed, vertical_speed, lat,
        lon)
        logger.info(f"Appending packet: {packet}")
        packets.append(packet)

    id_table_name = "drone_list"
    data_table_name = "remoteid_packets"

    item_count = 0
    with conn.cursor() as cur:

        # Add data from packets to database
        for pkt in packets:
            src_addr = pkt[0]  # TODO: change
            id = pkt[1]  # TODO: change
            timestamp = pkt[2]  # TODO: change
            heading = pkt[3]
            ground_speed = pkt[4]
            vertical_speed = pkt[5]
            lat = pkt[6]
            lon = pkt[7]

            sql_string = f"INSERT INTO {id_table_name:s}(src_addr, unique_id, lastTime) VALUES('{src_addr:s}', '{id:s}', '{timestamp:s}');"
            logging.info(f"SQL QUERY: {sql_string}")
            try:
                cur.execute(sql_string)
            except pymysql.err.IntegrityError as e:
                logger.warning("WARNING: MySQL IntegrityError")
                logger.warning(e)
            except pymysql.err.OperationalError as e:
                logger.error("ERROR: MySQL OperationalError")
                logger.error(e)
            # TODO: except loss of connection "errorMessage": "(0, '')", "errorType": "InterfaceError",

            sql_string = f"INSERT INTO {data_table_name:s}(src_addr, unique_id, timestamp, heading, gnd_speed, vert_speed, lat, lon) VALUES('{src_addr:s}', '{id:s}', '{timestamp:s}', {heading:d}, {ground_speed:d}, {vertical_speed:d}, {lat:d}, {lon:d});"
            logging.info(f"SQL QUERY: {sql_string}")
            try:
                cur.execute(sql_string)
            except pymysql.err.IntegrityError as e:
                logger.warning("WARNING: MySQL IntegrityError")
                logger.warning(e)

            cur.execute("SET SQL_SAFE_UPDATES=0;")  # Disable safe updates
            sql_string = f"UPDATE {id_table_name:s} SET lastTime='{timestamp:s}' WHERE '{timestamp:s}' > (SELECT lastTime FROM {id_table_name:s} WHERE src_addr='{src_addr:s}');"
            logging.info(f"SQL QUERY: {sql_string}")
            cur.execute(sql_string)
            cur.execute("SET SQL_SAFE_UPDATES=1;")  # Enable safe updates

        conn.commit()

        # Log items that were added
        cur.execute(f"SELECT * FROM {id_table_name:s}")
        logger.info("The following items are in the database:")
        for row in cur:
            item_count += 1
            logger.info(row)
    conn.commit()

    return {
        "StatusCode": 200,
        "Body": json.dumps(f"Added {item_count:d} items to the database")
    }