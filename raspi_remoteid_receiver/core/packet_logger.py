import logging
import multiprocessing
import os
import queue
import signal
import sys
import time
import traceback

import pyshark

from raspi_remoteid_receiver.core import helpers, setup_logging


class PacketLoggerProcess(multiprocessing.Process):
    def __init__(
            self, wifi_interface_queue: multiprocessing.Queue,
            bt_interface_queue: multiprocessing.Queue,
            packet_queue: multiprocessing.Queue,  # TODO: change to Pipe
            log_queue: multiprocessing.Queue,
            logging_level: int,
            use_wifi: bool, use_bt: bool,
            pcap_timeout_event: multiprocessing.Event,
            sleep_event: multiprocessing.Event,
            packet_timeout: int | float = 900,
            sleep_timeout: int | float = 3600,
            interface_timeout: int | float = 60,
            **kwargs,
    ):
        super().__init__(**kwargs)
        # Multiprocessing Queues
        self.wifi_interface_queue = wifi_interface_queue
        self.bt_interface_queue = bt_interface_queue
        self.packet_queue = packet_queue

        # Logging
        self.log_queue = log_queue
        self.logging_level = logging_level
        self.verbose_output = logging_level <= logging.INFO

        self.use_wifi = use_wifi
        self.use_bt = use_bt
        self.pcap_timeout_event = pcap_timeout_event
        self.sleep_event = sleep_event
        self.packet_timeout = packet_timeout
        self.sleep_timeout = sleep_timeout
        self.interface_timeout = interface_timeout

        self.interfaces = []
        self.cap = None
        self.logger = None

        self.total_packets = 0
        self.skipped_packets = 0
        self.verbose_output = False
        self.watchdog = None

    def setup_logger(self):
        self.logger = setup_logging.get_logger(
            __name__, self.log_queue, logging_level=logging.INFO,
        )
        setup_logging.logging_test(self.logger)

    def start_watchdog(self):
        """Creates a daemon thread which sends a SIGALRM signal to the
        calling process when the watchdog timer expires."""
        self.watchdog = helpers.WatchdogTimer(
            self.packet_timeout,
            callback=os.kill,
            callback_args=(self.pid, signal.SIGALRM),
            timer=time.monotonic,
            daemon=True,
        )
        self.watchdog.start()

    def setup_packet_logger(self) -> None:
        """Sets up packet logger using pyshark."""

        # Wait for Wi-Fi interface to be setup
        if self.use_wifi:
            try:
                wifi_interface = self.wifi_interface_queue.get(
                    timeout=self.interface_timeout,
                )
            except queue.Empty:
                self.logger.error(
                    "Timed out waiting for Wi-Fi monitor mode interface "
                    "to setup.",
                )
            else:
                if wifi_interface is not None:
                    self.interfaces.append(wifi_interface)

        # Wait for Bluetooth interface to be setup
        if self.use_bt:
            try:
                bt_interface = self.bt_interface_queue.get(
                    timeout=self.interface_timeout,
                )
            except queue.Empty:
                self.logger.error(
                    "Timed out waiting for Bluetooth monitor mode "
                    "interface to setup.",
                )
            else:
                if bt_interface is not None:
                    self.interfaces.append(bt_interface)

        # Check if interface list is empty
        if not self.interfaces:
            error_msg = "No interfaces were set up. Can't log packets."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Setup live packet capture
        self.logger.info(
            f"Setting up live capture with interfaces: {self.interfaces}",
        )
        try:
            self.cap = pyshark.LiveCapture(
                interface=self.interfaces,
                display_filter="opendroneid",
            )
        except Exception as e:
            self.logger.error(f"Error setting up packet capture: {e}")
            raise Exception from e

    @staticmethod
    def get_pkt_summary(pkt) -> str:
        """Returns a summary string of RF information from a packet for
        debugging.
        """
        try:
            wlan_radio = pkt.wlan_radio
        except AttributeError:
            try:
                nordic_ble = pkt.nordic_ble
            except AttributeError:
                # TODO: check Bluetooth 4 Legacy Advertising
                return "Unknown Physical Layer Protocol"
            proto_str = "BLE"
            ch = getattr(nordic_ble, "channel", "Unknown")
            # TODO: make sure RSS and RSSI are the same or convert if not
            rss = getattr(nordic_ble, "rssi", "Unknown")
        else:
            proto_str = "Wi-Fi"
            # Returns "Unknown" if wlan_radio.channel doesn't exist
            ch = getattr(wlan_radio, "channel", "Unknown")
            rss = getattr(wlan_radio, "signal_dbm", "Unknown")

        return f"{proto_str}, CH: {ch}, RSS: {rss} dBm"

    def put_in_queue(self, pkt) -> None:
        """Tries to put a packet into the packet queue. If the queue is full,
        the packet gets dropped.
        """
        with self.watchdog.lock:
            if self.verbose_output:
                self.logger.info(
                    "Received Packet: %s",
                    self.get_pkt_summary(pkt),
                )
            try:
                self.packet_queue.put(pkt, block=False)
            except queue.Full:
                self.skipped_packets += 1
            # Maybe put in finally block?
            self.total_packets += 1
            self.watchdog.reset()

    def wait_for_packets(self):
        # Continuously put packets into the queue
        self.logger.info("Waiting for packets...")
        while True:
            try:
                self.cap.apply_on_packets(self.put_in_queue)
            except TimeoutError:
                self.logger.info(
                    "Timed out waiting for a new Remote ID packet.",
                )
                break
            finally:
                self.cap.close()

        self.logger.info(
            f"Total captured packets: {self.total_packets}. "
            f"Total skipped packets: {self.skipped_packets}.",
        )

    def signal_handler(self, sig, frame):
        match sig:
            case signal.SIGINT:
                raise KeyboardInterrupt
            case signal.SIGALRM:  # note ALRM not ALARM
                raise TimeoutError

    def run(self) -> None:
        self.setup_logger()
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGALRM, self.signal_handler)
        try:
            self.setup_packet_logger()
            self.start_watchdog()
            self.wait_for_packets()
        except KeyboardInterrupt:
            self.logger.error("KeyboardInterrupt caught.")
        except Exception as exc:
            self.logger.error(traceback.format_exception(exc, limit=None))
            traceback.print_exception(exc, limit=None, file=sys.stderr)
        finally:
            self.pcap_timeout_event.set()
            self.sleep_event.set()
            try:
                self.packet_queue.put(None, block=False)
            except queue.Full:
                pass
            self.logger.error("Exiting process...")
