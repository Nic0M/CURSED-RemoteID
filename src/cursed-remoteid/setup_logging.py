import logging
from pathlib import Path

root_logging_level = logging.INFO


def setup_logging(root_level=logging.DEBUG):
    """Configures logging"""

    # Set the root logging level. No other loggers can log a message below this
    # level
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)

    # Format the log message
    # Log format: timestamp, logger name, log level, message
    # Timestamp format: year-month-day timezone hour:minute:second.milliseconds
    # Example: 2024-03-08 UTC-0700 11:41:54.587  __main__    [ERROR] error msg
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)3d  %(name)-15s  [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d UTC%z %H:%M:%S")

    # Create a stream handler log ERROR or above to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)

    # Create a logs directory if it doesn't already exist
    Path("logs").mkdir(parents=True, exist_ok=True)
    # Create a file handler which logs all the way to DEBUG
    file_handler = logging.FileHandler("logs/debug.log")
    file_handler.setLevel(root_level)
    file_handler.setFormatter(formatter)

    # Apply the console handler and file handler to the root handler to apply
    # these settings by default to all handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger.info(f"Root logger setup with logging level {root_level}.")


def logging_test():
    logger.debug("This is a debug message test and can be safely ignored.")
    logger.info("This is an info message test and can be safely ignored.")
    logger.warning("This is a warning message test and can be safely ignored.")
    logger.error("This is an error message test and can be safely ignored.")
    logger.critical("This is critical message test and can be safely ignored.")


setup_logging(root_level=root_logging_level)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)