import json
import logging
import os
import urllib.parse
import threading
import queue

import boto3
import pymysql

# Set logging levels
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# logger.setLevel(logging.CRITICAL) # TODO: enable when production


def get_database_credentials():
    """Reads the Lambda environment variables to get the RDS database
    credentials.
    """

    logger.info(
        "Attempting to retrieve database credentials from"
        "local environment variables.",
    )
    try:
        user = os.environ["DB_USER_NAME"]
        pwd = os.environ["DB_PASSWORD"]
        host = os.environ["RDS_HOST"]
        db = os.environ["DB_NAME"]
    except KeyError as e:
        logger.critical(
            f"Could not retrieve database credentials from environment "
            f"variables. {repr(e):s}.",
        )
        return None, None, None, None

    logger.info(
        "SUCCESS: Found database credentials in environment variables.",
    )
    return user, pwd, host, db


def connect_to_database(user, pwd, host, db):
    """Attempt to connect to RDS database. Returns the connection object if
    successful. Returns None if unsuccessful.
    """

    logger.info(f"Attempting to connect to database: {db} at host: {host}")
    try:
        connection = pymysql.connect(
            host=host, user=user, password=pwd, database=db,
            connect_timeout=5,  # 5 seconds
        )
    except pymysql.MySQLError as e:
        logger.error(f"Could not connect to database: {e}")
        return None

    logger.info("SUCCESS: Connection to RDS for MySQL instance succeeded.")
    return connection


def create_s3_client():
    """Attempts to create an S3 client. Returns the client object if
    successful. Returns None otherwise."""

    logger.info("Attempting to create a boto3 S3 client.")
    try:
        s3_client_obj = boto3.client("s3")
    except Exception as e:
        logger.error(f"Failed to create a boto3 S3 client: {e}")
        return None

    logger.info("SUCCESS: Created boto3 S3 client.")
    return s3_client_obj


# Get database credentials
user_name, password, rds_proxy_host, db_name = get_database_credentials()
# Attempt to establish persistent connection to database
if user_name is not None:
    conn = connect_to_database(user_name, password, rds_proxy_host, db_name)
else:
    conn = None
s3_client = create_s3_client()


def execute_query(query, cursor):
    """Executes a SQL query. Raises RuntimeError if database connection
    closes."""

    try:
        cursor.execute(query)
    except pymysql.err.IntegrityError as e:
        logger.warning(f"Duplicate data: {e}")
    except pymysql.err.OperationalError as e:
        logger.error(f"Unexpected MySQL OperationalError: {e}")
        logger.error(f"Check syntax of SQL statement: {query}")
        raise RuntimeError
    except pymysql.err.ProgrammingError as e:
        if not cursor:
            logger.error("Cursor was already closed.")
            raise RuntimeError
        logger.error(f"Unexpected MySQL ProgrammingError: {e}")
    except pymysql.err.InterfaceError as e:
        # Likely connection issue?
        logger.critical(f"Unexpected MySQL InterfaceError: {e}")
        raise RuntimeError
    except pymysql.err.MySQLError as e:
        logger.error(f"Unexpected MySQL Error: {e}")


def execute_queries(query_queue, cursor, timeout=2):
    """Function for executing SQL queries asynchronously. Times out after 2
    seconds of no new data."""
    global conn

    count = 0
    try:
        while True:
            query = query_queue.get(timeout=timeout)
            try:
                execute_query(query, cursor)
            except RuntimeError:
                break
            if count % 10 == 0:
                conn.commit()
            count += 1
    except queue.Empty:
        pass


def lambda_handler(event, context):
    """Reads data from an S3 bucket and writes the data to the database.
    """
    global conn  # this variable can get updated in the lambda_handler function
    global s3_client
    global index_map

    logging.info(f"Received event: {json.dumps(event, indent=2)}")

    if user_name is None:
        return {
            "Status Code": 502,
            "Body": "Couldn't find database credentials.",
        }

    if s3_client is None:
        logger.critical("boto3 client for S3 doesn't exist. ")
        return {
            "Status Code": 502,
            "Body": "Fatal error: s3 client object doesn't exist.",
        }

    logger.info("Attempting to extract bucket info from Lambda event.")
    try:
        # Get the object from the event and show its content type
        bucket = event['Records'][0]['s3']['bucket']['name']
        # Get the filename
        key = urllib.parse.unquote_plus(
            event['Records'][0]['s3']['object']['key'], encoding='utf-8',
        )
    except KeyError as e:
        logger.error(
            "Invalid record in event. Make sure the lambda function "
            f"is triggered from an S3 upload. {e}",
        )
        return {
            "Status Code": 400,
            "Body": "Invalid event passed to lambda function.",
        }
    logger.info("SUCCESS: Parsed record in event successfully.")

    logger.info("Attempting to get object from bucket.")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except s3_client.exceptions.NoSuchKey:
        logger.error(f"Object '{key}' does not exist in bucket '{bucket}'.")
        return {
            "Status Code": 400,
            "Body": "Invalid event passed to lambda function.",
        }
    except s3_client.exceptions.InvalidObjectState:
        return {
            "Status Code": 409,
            "Body": "Invalid Object State.",
        }
    logger.info(
        "Retrieved object successfully. "
        f"CONTENT TYPE: {response['ContentType']}",
    )

    if conn is None or not conn.open:
        logger.warning(
            "Database connection is not open. "
            "Attempting to reconnect to database.",
        )
        conn = connect_to_database(
            user_name, password, rds_proxy_host, db_name,
        )
        if conn is None:
            logger.error("Couldn't reconnect to database.")
            return {
                "Status Code": 502,
                "Body": "Couldn't establish connection to database.",
            }
        logger.info("SUCCESS: Reconnected to database successfully.")

    try:
        file_body = response["Body"].read().decode("utf-8")
    except Exception as e:
        logger.error(f"Error decoding file: {e}")
    else:
        with conn.cursor() as cur:
            # Start a thread to execute SQL queries asynchronously
            sql_query_queue = queue.Queue(maxsize=1000)
            sql_thread = threading.Thread(
                target=execute_queries,
                args=(
                    sql_query_queue,
                    cur,
                ),
            )
            sql_thread.start()

            remote_id_data_table = "remoteid_packets"
            drone_list_table = "drone_list"

            queried_packets = 0
            skipped_packets = 0

            src_addr_idx = None
            unique_id_idx = None
            timestamp_idx = None
            heading_idx = None
            gnd_speed_idx = None
            vert_speed_idx = None
            speed_acc_idx = None
            lat_idx = None
            lon_idx = None
            horz_acc_idx = None
            geo_alt_idx = None
            geo_vert_acc_idx = None
            baro_alt_idx = None
            height_idx = None
            height_type_idx = None

            rows = file_body.split("\n")
            first_row = True
            for row in rows:
                data = row.replace("\r", "").split(",")
                # Header column row
                if first_row:
                    for idx, col_name in enumerate(data):
                        # This could probably be faster with a dictionary
                        match col_name:
                            case "Source Address":
                                src_addr_idx = idx
                            case "Unique ID":
                                unique_id_idx = idx
                            case "Timestamp":
                                timestamp_idx = idx
                            case "Heading":
                                heading_idx = idx
                            case "Ground Speed":
                                gnd_speed_idx = idx
                            case "Vertical Speed":
                                vert_speed_idx = idx
                            case "Speed Accuracy":
                                speed_acc_idx = idx
                            case "Latitude":
                                lat_idx = idx
                            case "Longitude":
                                lon_idx = idx
                            case "Horizontal Accuracy":
                                horz_acc_idx = idx
                            # Distance above WGS-84 ellipsoid. Approximately
                            # the same as height above mean sea level (MSL)
                            case "Geodetic Altitude":
                                geo_alt_idx = idx
                            case "Geodetic Vertical Accuracy":
                                geo_vert_acc_idx = idx
                            case "Barometric Altitude":
                                baro_alt_idx = idx
                            # Height above ground level (AGL) or above takeoff
                            # location
                            case "Height":
                                height_idx = idx
                            case "Height Type":
                                height_type_idx = idx
                            case _:
                                logger.info(f"Unrecognized column: {col_name}")
                    first_row = False
                    continue

                if len(data) < 8:
                    logger.info(f"Skipping row with data: {data}")
                    skipped_packets += 1
                    continue
                try:
                    # Metadata
                    src_addr = data[src_addr_idx]
                    unique_id = data[unique_id_idx]
                    timestamp = data[timestamp_idx]  # TODO: validate timestamp

                    # Velocity
                    heading = int(data[heading_idx])
                    gnd_speed = float(data[gnd_speed_idx])
                    vert_speed = float(data[vert_speed_idx])
                    speed_acc = data[speed_acc_idx]
                    if not speed_acc:
                        speed_acc = "NULL"
                    else:
                        speed_acc = int(speed_acc)

                    # Horizontal Position
                    lat = int(data[lat_idx]) / 1e7  # Implicit float cast
                    lon = int(data[lon_idx]) / 1e7  # Implicit float cast
                    horz_acc = data[horz_acc_idx]
                    if not horz_acc:
                        horz_acc = "NULL"
                    else:
                        horz_acc = int(horz_acc)

                    # Altitude
                    geo_alt = data[geo_alt_idx]
                    if not geo_alt:
                        geo_alt = "NULL"
                    else:
                        geo_alt = float(geo_alt)
                    geo_vert_acc = data[geo_vert_acc_idx]
                    if not geo_vert_acc:
                        geo_vert_acc = "NULL"
                    else:
                        geo_vert_acc = int(geo_vert_acc)
                except ValueError as e:
                    skipped_packets += 1
                    continue
                except IndexError as e:
                    skipped_packets += 1
                    logger.error(f"Probably issue with code: {e}")
                    continue

                try:
                    # These values are not required to be transmitted in
                    # ASTM F3411-22a. Empty string "" has a value of False.
                    if not data[baro_alt_idx]:
                        baro_alt = "NULL"
                    if data[height_idx] and data[height_type_idx]:
                        height = float(data[height_idx])
                        height_type = data[height_type_idx]
                    else:
                        height = "NULL"
                        height_type = "NULL"
                except ValueError as e:
                    skipped_packets += 1
                    continue
                except IndexError as e:
                    skipped_packets += 1
                    logger.error(f"Probably issue with code: {e}")
                    continue
                except TypeError:
                    # If index is None, you get a TypeError
                    baro_alt = "NULL"
                    height = "NULL"
                    height_type = "NULL"

                sql_query = (
                    f"INSERT INTO {remote_id_data_table} ("
                    f"src_addr, unique_id, timestamp, "
                    f"heading, gnd_speed, vert_speed, "
                    f"lat, lon, pressALT, geoAlt, "
                    f"height, hAccuracy, vAccuracy, "
                    f"speedAccuracy) "
                    f"VALUES ("
                    f"'{src_addr:s}', '{unique_id:s}', '{timestamp:s}', "  # can't use backticks for a string lol  # noqa
                    f"{heading:d}, {gnd_speed:.2f}, {vert_speed:.2f}, "
                    f"{lat:.6f}, {lon:.6f}, {baro_alt}, {geo_alt}, "
                    f"{height}, {horz_acc}, {geo_vert_acc}, "
                    f"{speed_acc})"
                )
                try:
                    sql_query_queue.put(sql_query, block=False)
                except queue.Full:
                    skipped_packets += 1
                else:
                    queried_packets += 1

            sql_thread.join()
            conn.commit()

            # TODO: execute SQL statement to get the latest time stamp
            # Also adds new drones to drone list
            # fmt: off
            sql_query = (
                f"INSERT INTO {drone_list_table} (src_addr, unique_id, lastTime) "  # noqa
                f"SELECT s.src_addr, s.unique_id, s.timestamp "
                f"FROM {remote_id_data_table} s "
                f"INNER JOIN ("
                f"  SELECT src_addr, MAX(timestamp) AS latest_timestamp "
                f"  FROM {remote_id_data_table}"
                f"  GROUP BY src_addr "
                f") AS grouped ON s.src_addr = grouped.src_addr AND s.timestamp = grouped.latest_timestamp "  # noqa
                f"ON DUPLICATE KEY UPDATE "
                f"unique_id=VALUES(unique_id), lastTime=VALUES(lastTime);"
            )
            # fmt: on
            try:
                execute_query(sql_query, cur)
            except RuntimeError:
                logger.error("Failed to update current drone list table.")
            else:
                conn.commit()

            # TODO: send HTTP POST TO Trackserver plugin

    logger.info(f"Queried {queried_packets:d} packets."
                f"Skipped {skipped_packets:}.")

    return {
        "StatusCode": 200,
        "Body": "OK",
    }
