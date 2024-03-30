import os
from pathlib import Path
import threading
import time

from raspi_remoteid_receiver.core import setup_logging


class WatchdogTimer(threading.Thread):
    """Class for creating a watchdog timer thread."""

    def __init__(
            self, timeout, callback, callback_args=(), timer=time.monotonic,
            **kwargs,
    ) -> None:
        """Initialization function for WatchdogTimer class.

        :param timeout: watchdog timeout in seconds
        :param callback: function to call when timeout occurs
        :param args: arguments to pass into callback function
        :param timer: function to call to get the current time in seconds
        :param kwargs: thread arguments
        """
        super().__init__(**kwargs)
        self._timeout = timeout
        self._callback = callback
        self._args = callback_args
        self._timer = timer
        self._disabled = threading.Event()
        self._lock = threading.Lock()
        self._deadline = None

    def run(self):
        """Automatically runs on thread start."""
        self.reset()
        time_remaining = self._deadline - self._timer()
        # threading.Event.wait(timeout) blocks until event is set or timeout
        # occurs. If event is set, returns True, if timeout occurs, returns
        # False
        while not self._disabled.wait(timeout=time_remaining):
            # Timeout occurred, but reset may have occurred
            with self._lock:
                if self._deadline <= self._timer():
                    if self._callback is not None:
                        return self._callback(*self._args)
        # If this is reached, watchdog timer was disabled
        return None

    def reset(self):
        """Resets the watchdog timer by setting the timeout time to the
        current time plus the timeout in seconds."""
        self._deadline = self._timer() + self._timeout

    def disable(self):
        """Disables the watchdog timer by setting a threading event."""
        self._disabled.set()

    @property
    def lock(self):
        """Lock is public attribute."""
        return self._lock


def safe_remove_csv(file_name: str) -> True:
    """Permanently deletes the file at 'file_name'. Returns True if deleted,
    returns False otherwise."""
    logger = setup_logging.get_process_logger(__name__)
    if Path(file_name).suffix != ".csv":
        logger.error(
            f"safe_remove: detected file extension is not .csv. "
            f"File {file_name} will not be deleted.",
        )
        return False
    try:
        os.remove(file_name)
    except FileNotFoundError:
        logger.warning(
            f"Attempted to delete file {file_name} but the file"
            f"doesn't exit.",
        )
        return False
    except OSError as e:
        logger.error(
            f"Failed to remove file {file_name}. "
            f"Error: {e.strerror}",
        )
        return False
    logger.info(f"Deleted file {file_name} successfully.")
    return True
