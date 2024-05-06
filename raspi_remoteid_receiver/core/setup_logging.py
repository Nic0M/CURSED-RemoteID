import logging
import logging.handlers
import multiprocessing
from pathlib import Path


def get_logging_formatter() -> logging.Formatter:
    # Format the log message
    # Log format: timestamp, logger name, log level, message
    # Timestamp format: year-month-day timezone hour:minute:second.milliseconds
    # Example: 2024-03-08 UTC-0700 11:41:54.587  __main__    [ERROR] error msg
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)3d  %(name)-50s  [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d UTC%z %H:%M:%S",
    )
    return formatter


def setup_logging(
    *,
    log_queue: multiprocessing.Queue,
    root_level: int = logging.DEBUG,
    console_level: int = logging.WARNING,
    file_level: int = logging.INFO,
    log_file: str = "logs/debug.log",
) -> logging.handlers.QueueListener:
    """Configures logging.

    :param log_queue: Required keyword argument.
    :param root_level: Minimum logging level that all loggers inherit from
    :param console_level: Logging level to console.
    :param file_level: Logging level to file.
    :param log_file: Name of log file (with relative path)
    :return: QueueListener handler with console and file output
    """

    # Set the root logging level. No other loggers can log a message below this
    # level
    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)

    formatter = get_logging_formatter()

    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setFormatter(formatter)

    # Create a stream handler and log CONSOLE_LEVEL or above to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    # Create file handler and log FILE_LEVEL or above to the file
    # Create directory if it doesn't already exist
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    listeners = [
        console_handler,
        file_handler,
    ]

    queue_listener = logging.handlers.QueueListener(
        log_queue,
        *listeners,
        respect_handler_level=True,
    )
    return queue_listener


def get_logger(
        name: str,
        log_queue: multiprocessing.Queue,
        logging_level: int | None = None,
) -> logging.Logger:
    """Returns a logger that uses the log queue for safe logging in multiple
    processes."""
    queue_handler = logging.handlers.QueueHandler(log_queue)
    logger = logging.getLogger(name)
    logger.addHandler(queue_handler)
    if logging_level is not None:
        logger.setLevel(logging_level)
    logger.propagate = False
    return logger


def logging_test(logger) -> None:
    """Method for testing all logging levels."""
    logger.debug("This is a debug message test and can be safely ignored.")
    logger.info("This is an info message test and can be safely ignored.")
    logger.warning("This is a warning message test and can be safely ignored.")
    logger.error("This is an error message test and can be safely ignored.")
    logger.critical("This is critical message test and can be safely ignored.")
