import subprocess
import re
import os
import logging
import time
import queue

logger = logging.getLogger(__name__)


class InvalidInterfaceName(Exception):
    pass


class NoSupportedChannels(Exception):
    pass


class InterfaceNoLongerInMonitorMode(Exception):
    pass


class IllegalChannel(Exception):
    pass


class CommandNotFound(Exception):
    pass


class ChannelDictionary:
    def __init__(self, channel_queue, supported_channels):
        self.queue = channel_queue
        self.supported_channels = supported_channels

        # Use default channels
        self.channels = []
        self.use_default_sweep()

        self.ch_pkt_count = self._create_channel_packet_count()        

    def use_default_sweep(self):
        self.channels = [
            ("1", 0.5),
            ("6", 0.5),
            ("11", 0.5),
            ("36", 0.25),
            ("40", 0.25),
            ("44", 0.25),
            ("48", 0.25),
            ("1", 0.5),
            ("6", 0.5),
            ("11", 0.5),
            ("149", 0.25),
            ("153", 0.25),
            ("157", 0.25),
            ("161", 0.25),
        ]

    @staticmethod
    def _create_channel_packet_count():
        two_ghz_chs = list(range(1, 14))  # Channels 1-13
        lower_five_ghz_chs = list(range(36, 49, 4))  # 36, 40, 44, 48
        upper_five_ghz_chs = list(range(149, 162, 4))  # 149, 153, 157, 161
        channels = two_ghz_chs + lower_five_ghz_chs + upper_five_ghz_chs

        ch_pkt_count = {}
        for ch in channels:
            ch_pkt_count[str(ch)] = 0
        return ch_pkt_count

    def reset_channel_packet_count(self):
        for channel in self.ch_pkt_count:
            self.ch_pkt_count[channel] = 0

    def update(self):
        """Updates the channel sweep"""

        queue_is_empty = False
        while not queue_is_empty:
            try:
                ch = self.queue.get(block=False)
            except queue.Empty:
                queue_is_empty = True
                continue
            self.ch_pkt_count[str(ch)] += 1

        # TODO: do something with the number of Remote ID packets received on
        # TODO: each channel

    def get_channels(self):
        return self.channels

    def remove(self, channel):
        self.supported_channels = [x for x in self.supported_channels
                                   if x != channel]
        self.channels = [(ch, t) for (ch, t) in self.channels
                         if ch != channel]


def sanitize_physical_interface_name(phy_name):
    """Sanitizes interface name. Throws InvalidInterfaceName error if invalid.
    Example valid interface names:
    - phy0
    - phy2
    - phy11
    Example invalid interface names:
    - phy
    - wlan0
    - [phy0]
    - phy1wlan1mon
    """
    interface_name = phy_name.strip()
    if not re.match(r"^phy\d+$", interface_name):
        raise InvalidInterfaceName(interface_name)
    return interface_name


def sanitize_mon_interface_name(mon_name):
    """Sanitizes interface name. Throws InvalidInterfaceName error if invalid.
    Example valid interface names:
    - wlan0
    - wlan0mon
    - wlan1
    - wlan99mon
    Example invalid interface names:
    - wlan
    - mon0
    - wlanmon
    - en0
    - eth0
    """
    interface_name = mon_name.strip()
    if not re.match(r"^wlan[0-9]+(mon)?$", interface_name):
        raise InvalidInterfaceName(interface_name)
    return interface_name


def get_supported_channel_list(phy, mon):
    """Returns the list of channels that the network interface supports.
    Returns None if there are no supported channels.
    """

    # Sanitize interface name input since running with shell=True
    try:
        phy = sanitize_physical_interface_name(phy)
    except InvalidInterfaceName:
        logger.error(f"Invalid physical interface name: {phy}")
        return None
    try:
        mon = sanitize_mon_interface_name(mon)
    except InvalidInterfaceName:
        logger.error(f"Invalid monitor interface name: {mon}")
        return None

    # Validate physical wireless interface name
    phy_file_name = f"/sys/class/net/{mon}/phy80211/name"
    if not os.path.exists(phy_file_name):
        logger.error(f"Ensure that {phy_file_name} exists.")
        return None
    phy_name_cmd = f"cat \"{phy_file_name}\" 2>&1"  # Prints file contents
    logger.info(f"Running command: {phy_name_cmd}")
    try:
        output = subprocess.check_output(phy_name_cmd, shell=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"CalledProcessError: {e}")
        logger.error(f"STDOUT: {e.stdout}")
        return None
    output = output.strip()
    if phy != output:
        logger.error(f"Given interface {phy} doesn't match {output}.")
        return None

    # Get the supported channels separated by new lines (from airmon-ng code)
    # Standard error is redirected to standard output
    get_channels_cmd = f"iw phy {phy} channels 2>&1"

    logger.info(f"Running command: {get_channels_cmd}")
    try:
        output = subprocess.check_output(get_channels_cmd,
                                         shell=True,
                                         text=True,  # Makes output a string,
                                         )
    except subprocess.CalledProcessError as e:
        logger.error(f"CalledProcessError: {e}")
        if e.returncode == 127:
            logger.error("Ensure that iw is installed and correctly added to "
                         "PATH.")
        logger.error(f"STDOUT: {e.stdout}")
        return None
    lines = output.strip().split('\n')
    supported_channels_list = []
    # For every line, get the first number inside brackets on the line
    for line in lines:
        # Separate line by brackets: '[' or ']'
        fields = re.split(r'\[|\]', line)

        # If there are at least three elements, there is a channel enclosed
        # by brackets, which is the second element (Python is 0-indexed).
        if len(fields) > 2:
            supported_channels_list.append(fields[1])

    # Check if list is empty
    if not supported_channels_list:
        logger.error(f"No supported channels on interface {mon}.")
        return None
    logger.info(f"Supported channel list: {supported_channels_list}.")
    return supported_channels_list


def set_channel(mon, channel):

    mon = sanitize_mon_interface_name(mon)
    channel = str(channel)

    # Sanitize channel input since running with shell=True
    if not channel.isdigit():
        logger.error(f"Channel: {channel} is not a number. Cannot set "
                     f"monitor interface {mon} to that channel.")
        raise ValueError(channel)

    set_channel_cmd = f"iw dev {mon} set channel {channel} 2>&1"
    logger.info(f"Running command: {set_channel_cmd}")
    try:
        subprocess.check_output(set_channel_cmd, shell=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to switch to channel {channel}.")
        logger.error(f"STDOUT: {e.stdout}")
        if "(-16)" in e.output:
            logger.error(f"Interface {mon} is likely no longer in "
                         f"monitor mode.")
            raise InterfaceNoLongerInMonitorMode(mon)
        elif "(-22)" in e.output:
            logger.error(f"Channel {channel} cannot be legally used.")
            raise IllegalChannel(channel)
        elif e.returncode == 127:
            logger.error(f"Command not found. Likely missing 'iw'")
            raise CommandNotFound(set_channel_cmd)
        else:
            raise Exception(e)
    logger.info(f"Switched to channel {channel} successfully.")
    return channel


def setup_wifi_interface(mac_addr):

    # Kill any network processes that might interfere with monitor mode
    check_kill_cmd = "sudo airmon-ng check kill"
    try:
        subprocess.run(check_kill_cmd, shell=True)
    except subprocess.CalledProcessError as e:
        logger.error(e)
        logger.error(e.output)
        raise Exception  # TODO: make less generic

    # Possible interface names for the external Wi-Fi network card
    long_interface_name = f"wlx{mac_addr}"
    short_interface_name = "wlan1"  # wlan0 is the built-in Wi-Fi card on Pi
    # TODO: ALSO TRY wlan1mon

    cmd_long_name = f"sudo airmon-ng start {long_interface_name} 2>&1"
    cmd_short_name = f"sudo airmon-ng start {short_interface_name} 2>&1"

    logger.info(f"Trying to use long name: {cmd_long_name}")
    try:
        output = subprocess.check_output(cmd_long_name, shell=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        logger.error(f"STDOUT: {e.stdout.rstrip()}")
        if "sudo: a password is required" in e.output:
            logger.critical("Insufficient permission to run script.")
            raise PermissionError
        elif "command not found" in e.output:
            logger.error("Ensure that airmon-ng is installed. "
                         "Try 'sudo apt install aircrack-ng'")
            raise CommandNotFound("airmon-ng")
        elif "No such device" in e.output:
            logger.info(f"Trying to use short name: {cmd_short_name}")
            try:
                output = subprocess.check_output(cmd_short_name, shell=True, text=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error: {e}")
                raise Exception  # TODO: make less generic
        else:
            raise Exception  # TODO: make less generic

    # Get the physical wireless interface name and the monitoring interface
    regex_str = r"\[(phy\d+)\](wlan\d+mon)"
    match = re.search(regex_str, output)
    if match:
        phy_name = match.group(1)
        mon_name = match.group(2)
    else:
        logger.error(f"No regex match found in output with regex: {regex_str}")
        logger.error(f"Output: {output}")
        raise Exception  # TODO: make less generic
    logger.info(f"phy: {phy_name}, mon: {mon_name}")
    return phy_name, mon_name


def wifi_channel_sweeper(phy, mon, channel_queue, sleep_event):

    supported_channels = get_supported_channel_list(phy, mon)
    if supported_channels is None:
        raise NoSupportedChannels(str((phy, mon)))

    logger.info("Creating channel dictionary.")
    channel_dict = ChannelDictionary(channel_queue, supported_channels)

    while not sleep_event.is_set():
        for channel, scan_time in channel_dict.get_channels():
            try:
                set_channel(mon, channel)
            except IllegalChannel as e:
                logger.error(f"Removing illegal channel {channel} from "
                             f"channel list.")
                channel_dict.remove(channel)
                continue
            except ValueError as e:
                logger.error(f"Invalid channel number: {e}")
                channel_dict.remove(channel)
                continue
            except InterfaceNoLongerInMonitorMode as e:
                raise RuntimeError(e)
            except CommandNotFound as e:
                raise RuntimeError(e)

            time.sleep(scan_time)
        channel_dict.update()

    logger.info("Sleep event received.")
    return None


def main(mac_addr, wifi_interface_queue, bt_interface_queue, channel_queue,
         sleep_event):
    """Main entry point for channel selection thread."""

    logger.info("Started channel selection thread.")

    # Try to set up Wi-Fi interface
    try:
        phy, mon = setup_wifi_interface(mac_addr)
    except Exception as e:
        logger.critical(f"Error setting up Wi-Fi interface: {e}")
        return 1
    try:
        wifi_interface_queue.put(mon, block=False)
    except queue.Full:  # This shouldn't be possible
        logger.critical("Wi-Fi interface queue is somehow full. Cannot notify"
                        "other threads of successful setup.")
        return 1

    # Try to set up Bluetooth interface
    bt_interface_name = "bluetooth-monitor"  # TODO: add nRF name
    try:
        bt_interface_queue.put(bt_interface_name, block=False)
    except queue.Full:  # This shouldn't be possible
        logger.critical("Bluetooth interface queue is somehow full. Cannot"
                        "notify other threads of successful setup.")
        return 1

    logger.info("Set up network interfaces successfully.")

    # Sweep through Wi-Fi channels (Bluetooth channels can all be captured at
    # the same time)
    logger.info("Attempting to sweeping through Wi-Fi channels...")
    try:
        wifi_channel_sweeper(phy, mon, channel_queue, sleep_event)
    except NoSupportedChannels:
        logger.critical("No supported channels to sweep through.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

    logger.info("Exiting channel selection thread.")
    return 0
