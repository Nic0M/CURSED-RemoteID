import logging
import threading
import queue

import pyshark

logger = logging.getLogger(__name__)


class PacketLogger:
    """Class to keep stats on packets logged."""

    def __init__(
            self, packet_queue: queue.Queue, sigint_event: threading.Event,
    ):
        self.total_packet_count = 0
        self.skipped_packet_count = 0
        self.packet_queue = packet_queue
        self.sigint_event = sigint_event

    def put_in_queue(self, pkt):
        """Tries to put a packet into the packet queue. If the queue is full,
        the packet gets dropped."""
        if self.sigint_event.is_set():
            raise KeyboardInterrupt
        try:
            self.packet_queue.put(pkt, block=False)
        except queue.Full:
            self.skipped_packet_count += 1
        finally:
            self.total_packet_count += 1


def packet_logger(
    wifi_interface_queue,
    bt_interface_queue,
    packet_queue,
    use_wifi,
    use_bt,
    sigint_event,
    packet_timeout=900,
    interface_timeout=60,
):
    """Sets up packet logger using pyshark."""

    interfaces = []

    # Wait for Wi-Fi interface to be setup
    if use_wifi:
        try:
            wifi_interface = wifi_interface_queue.get(
                timeout=interface_timeout,
            )
        except queue.Empty:
            logger.error(
                "Timed out waiting for Wi-Fi monitor mode interface "
                "to setup.",
            )
        else:
            if wifi_interface is not None:
                interfaces.append(wifi_interface)

    # Wait for Bluetooth interface to be setup
    if use_bt:
        try:
            bt_interface = bt_interface_queue.get(timeout=interface_timeout)
        except queue.Empty:
            logger.error(
                "Timed out waiting for Bluetooth monitor mode "
                "interface to setup.",
            )
        else:
            if bt_interface is not None:
                interfaces.append(bt_interface)

    # Check if interface list is empty
    if not interfaces:
        logger.error("No interfaces were set up. Packet logger cannot start.")
        return None

    # Setup live packet capture
    logger.info(f"Setting up live capture with interfaces: {interfaces}")
    try:
        cap = pyshark.LiveCapture(
            interface=interfaces,
            display_filter="opendroneid",
        )
    except Exception as e:
        logger.error(f"Error setting up packet capture: {e}")
        raise Exception from e

    pkt_logger = PacketLogger(packet_queue, sigint_event)
    # Continuously put packets into the queue
    logger.info("Waiting for packets...")
    try:
        cap.apply_on_packets(pkt_logger.put_in_queue)
    except TimeoutError:  # TODO: implement timeout from packet_timeout
        logger.info("Timed out waiting for a new Remote ID packet.")
    except KeyboardInterrupt as e:
        if not sigint_event.is_set():
            raise KeyboardInterrupt from e
        logger.info("Detected SIGINT event set.")
        return None
    finally:
        cap.close()

    logger.info(
        f"Total captured packets: {pkt_logger.total_packet_count}. "
        f"Total skipped packets: {pkt_logger.skipped_packet_count}.",
    )

    return None


def main(
    wifi_interface_queue,
    bt_interface_queue,
    packet_queue,
    use_wifi,
    use_bt,
    pcap_timeout_event,
    sigint_event,
    sleep_event,
    packet_timeout=900,
    interface_timeout=60,
):
    """Main entry point for the packet logger thread."""

    try:
        packet_logger(
            wifi_interface_queue,
            bt_interface_queue,
            packet_queue,
            use_wifi,
            use_bt,
            sigint_event,
            packet_timeout,
            interface_timeout,
        )
    except Exception as e:
        logger.error(e)
    finally:
        # Ensure that csv writer knows this thread terminated
        pcap_timeout_event.set()
        sleep_event.set()  # kill channel swapper
        try:
            packet_queue.put(None, block=False)
        except queue.Full:
            pass
    logger.info("Exiting thread...")
    return 0
