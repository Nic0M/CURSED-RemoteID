import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def safe_remove(file_name):
    """Permanently deletes the file at 'file_name'"""
    if Path(file_name).suffix != ".csv":
        logger.error(f"safe_remove: detected file extension is not .csv. File {file_name} will not be deleted.")
        return
    try:
        os.remove(file_name)
    except FileNotFoundError:
        logger.warning(f"Attempted to delete file {file_name} but the file"
                       f"doesn't exit.")
    except OSError as e:
        logger.error(f"Failed to remove file {file_name}. "
                     f"Error: {e.strerror}")
    logger.info(f"Deleted file {file_name} successfully.")
    return
