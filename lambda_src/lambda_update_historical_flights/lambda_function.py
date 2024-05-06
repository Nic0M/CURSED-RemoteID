import json
# import urllib.parse
# import boto3
# from botocore.exceptions import ClientError
import logging
import os
# import sys
import pymysql

# Set logging levels
logger = logging.getLogger()
logger.setLevel(
    logging.DEBUG,
)  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL


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
            f"ERROR: Could not retrieve database credentials from "
            f"environment variables. {repr(e):s}.",
        )
        return None, None, None, None

    logger.info(
        "SUCCESS: Found database credentials in environment variables.",
    )
    return user, pwd, host, db


# Get database credentials
user_name, password, rds_proxy_host, db_name = get_database_credentials()


def connect_to_database(user, pwd, host, db):
    """Attempts to connect to RDS database. Returns the connection object if
    successful. Returns None if unsuccessful"""

    # logging.debug("DEBUG: Skipping database connection attempt.")
    # return None

    try:
        connection = pymysql.connect(
            host=host, user=user, passwd=pwd, db=db,
            connect_timeout=5,
        )
    except pymysql.MySQLError as e:
        logger.error(
            "ERROR: Unexpected error: Could not connect to MySQL instance.",
        )
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


def lambda_handler(event, context):
    """This function reads data from an S3 bucket and writes the data to the
    database.
    """
    global conn  # this variable can get updated in the lambda_handler function

    logging.info("Received event: " + json.dumps(event, indent=2))

    if user_name is None:
        return 502

    if conn is None or not conn.open:
        logger.warning(
            "WARNING: Database connection doesn't exist. "
            "Attempting to reconnect to database.",
        )
        conn = connect_to_database(
            user_name, password, rds_proxy_host,
            db_name,
        )
        if conn is None:
            logger.error("ERROR: Couldn't reconnect to database.")
            return 502
        else:
            logger.info("SUCCESS: Reconnected to database successfully.")

    complete_table_name = "completed_flights"

    item_count = 0
    with conn.cursor() as cur:

        sql_string = f"INSERT INTO {complete_table_name} " \
            f"(src_addr, unique_id, duration, start_time, end_time," \
            f"max_gnd_speed, max_vert_speed, max_height_agl, " \
            f"max_alt) " \
            f"SELECT active_flights.src_addr, " \
            f"active_flights.unique_id, " \
            f"TIMESTAMPDIFF(second, active_flights.startTime, " \
            f"active_flights.currTime) as duration, " \
            f"active_flights.startTime, active_flights.currTime, " \
            f"max(remoteid_packets.gnd_speed) as max_gnd_speed, " \
            f"max(remoteid_packets.vert_speed) as max_vert_speed, " \
            f"max(remoteid_packets.height) as max_height_agl, " \
            f"max(remoteid_packets.geoAlt) as max_height_agl " \
            f"FROM active_flights,remoteid_packets " \
            f"WHERE active_flights.src_addr=remoteid_packets. " \
            f"src_addr and TIMESTAMPDIFF(second, " \
            f"active_flights.currTime,CURRENT_TIMESTAMP)>600;"
        logging.info(f"SQL QUERY: {sql_string}")
        try:
            cur.execute(sql_string)
        except pymysql.err.IntegrityError as e:
            logger.warning("WARNING: MySQL IntegrityError")
            logger.warning(e)
        except pymysql.err.OperationalError as e:
            logger.error("ERROR: MySQL OperationalError")
            logger.error(e)
        # TODO: except loss of connection "errorMessage":
        #  "(0, '')", "errorType": "InterfaceError",

        # sql_string = f"INSERT INTO {data_table_name:s}(src_addr, unique_id,
        # timestamp, heading, gnd_speed, vert_speed, lat, lon)
        # VALUES('{src_addr:s}', '{id:s}', '{timestamp:s}', {heading:d},
        # {ground_speed:d}, {vertical_speed:d}, {lat:d}, {lon:d});"
        # logging.info(f"SQL QUERY: {sql_string}")
        # try:
        #    cur.execute(sql_string)
        # except pymysql.err.IntegrityError as e:
        #    logger.warning("WARNING: MySQL IntegrityError")
        #    logger.warning(e)

        conn.commit()

        # Log items that were added
        cur.execute(f"SELECT * FROM {complete_table_name:s}")
        logger.info("The following items are in the database:")
        for row in cur:
            item_count += 1
            logger.info(row)
    conn.commit()

    return {
        "StatusCode": 200,
        "Body": json.dumps(f"Added {item_count:d} items to the database"),
    }
