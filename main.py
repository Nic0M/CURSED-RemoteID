__version__ = "0.1.0"

# import numpy as np
import subprocess


def get_channel_list():
    """Returns a list of Wi-Fi channels which Remote ID signals are expected
    to be broadcast on."""
    channels = [1, 6, 11, 36, 40, 44, 48, 149, 153, 157, 161]
    return channels


def main():

    # Default Wi-Fi channel to scan
    default_wifi_channel = 6

    # TODO: set up monitor mode
        # TODO: if dongle not connected, exit

    # TODO: start capture

    # Get list of Wi-Fi channels
    wifi_channel_list = get_channel_list()

    active_channel_list = []

    run_main_loop = True
    while run_main_loop:
        for channel in wifi_channel_list:
            # TODO: switch to channel
            # TODO: add sudo capability
            # TODO: add dict so not doing string conversion
            subprocess.run(["airmon-ng", "start", "wlan1mon", str(channel)])

            # TODO: wait for 1 second

            drone_detected = False
            # TODO: check for OpenDroneID message

            # If OpenDroneID message detected, add channel to active channels
            if drone_detected:
                active_channel_list.append(channel)
            else:
                # TODO: remove channel from active channel list if not already removed
                pass

    # TODO: end packet capture


if __name__ == "__main__":
    main()
