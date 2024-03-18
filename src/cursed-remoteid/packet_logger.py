import logging
import queue
import pyshark

logger = logging.getLogger(__name__)


class PacketLogger:
    def __init__(self, packet_queue):
        self.total_packet_count = 0
        self.skipped_packet_count = 0
        self.packet_queue = packet_queue

    def put_in_queue(self, pkt):
        try:
            self.packet_queue.put(pkt, block=False)
        except queue.Full:
            self.skipped_packet_count += 1
        finally:
            self.total_packet_count += 1


def packet_logger(wifi_interface_queue,
                  bt_interface_queue,
                  packet_queue,
                  packet_timeout=900,
                  interface_timeout=60,
                  ):

    # Wait for Wi-Fi interface to be setup
    try:
        wifi_interface = wifi_interface_queue.get(timeout=interface_timeout)
    except queue.Empty:
        logger.error("Timed out waiting for Wi-Fi monitor mode interface to "
                     "setup.")
        return 1

    # Wait for Bluetooth interface to be setup
    try:
        bt_interface = bt_interface_queue.get(timeout=interface_timeout)
    except queue.Empty:
        logger.error("Timed out waiting for Bluetooth monitor mode interface "
                     "to setup.")
        return 1

    # Setup live packet capture
    interfaces = [wifi_interface, bt_interface]
    logger.info(f"Setting up live capture with interfaces: {interfaces}")
    try:
        cap = pyshark.LiveCapture(interface=interfaces,
                                  display_filter="opendroneid")
    except Exception as e:
        logger.error(f"Error setting up packet capture: {e}")
        return 1

    pkt_logger = PacketLogger(packet_queue)
    # Continuously put packets into the queue
    logger.info("Waiting for packets...")
    try:
        cap.apply_on_packets(pkt_logger.put_in_queue)
    except TimeoutError:  # TODO: implement timeout from packet_timeout
        logger.info("Timed out waiting for a new Remote ID packet.")
    finally:
        cap.close()

    logger.info(f"Total captured packets: {pkt_logger.total_packet_count}. "
                f"Total skipped packets: {pkt_logger.skipped_packet_count}.")

    return None


def main(wifi_interface_queue,
         bt_interface_queue,
         packet_queue,
         pcap_timeout_event,
         packet_timeout=900,
         interface_timeout=60,
         ):
    """Main entry point for the packet logger thread."""

    try:
        packet_logger(wifi_interface_queue,
                      bt_interface_queue,
                      packet_queue,
                      packet_timeout,
                      interface_timeout,
                      )
    except Exception as e:
        logger.error(e)
        pass
    finally:
        # Ensure that csv writer knows this thread terminated
        pcap_timeout_event.set()
        try:
            packet_queue.put(None, block=False)
        except queue.Full:
            pass
    logger.info("Exiting thread...")
    return 0
