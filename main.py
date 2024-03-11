__version__ = "0.1.0"

# import numpy as np
import subprocess
import pyshark
import time


def get_channel_list():
    """Returns a list of Wi-Fi channels which Remote ID signals are expected
    to be broadcast on."""
    channels = ['1', '6', '11', '36', '40', '44', '48', '149', '153', '157', '161']
    return channels

def main():

    #determining the interface name
    # Use MAC address on the back of the network card adapter
    MAC_addr = "00c0cab400dd"

    long_interface_name = f"wlx{MAC_addr}"
    short_interface_name = 'wlan1mon'

    print(f"Long Interface Name: {long_interface_name}")
    print(f"Short Interface Name: {short_interface_name}")
    
    # TODO:  Check if monitor interface exists
    #if [ iwconfig "$long_interface_name" |& grep 'No such device' ] && [ iwconfig "$short_interface_name" |& grep 'No such device' ]; then
    #    echo "Didn't detect interface $long_interface_name or $short_interface_name"
    #    exit 1

    # Default Wi-Fi channel to scan
    default_wifi_channel = 6

    # TODO: set up monitor mode
        # TODO: if dongle not connected, exit
        # Command to run
    command_long = f"sudo airmon-ng start {long_interface_name} 1 && airmon-ng check kill"
    command_short = f"sudo airmon-ng start {short_interface_name} 1 && airmon-ng check kill"

    # Run the command to start monitor mode
    try:
        subprocess.run(command_short, shell=True, check=True)
        subprocess.run(command_long, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        
    # Get list of Wi-Fi channels
    wifi_channel_list = get_channel_list()

    active_channel_list = []

    initial_detection = True
    
    while initial_detection:
         # TODO: the file path created


        
        for channel in wifi_channel_list:
            # TODO: switch to channel
            # TODO: add sudo capability
            # TODO: add dict so not doing string conversion
            subprocess.run(["airmon-ng", "start", "wlan1mon", channel])
            print(f'Scanning Channel: {channel}')

             drone_detected = False
            # TODO: check for OpenDroneID message

            # TODO: wait for 1 second
            time.sleep(0.46)

            # If OpenDroneID message detected, add channel to active channels
            if drone_detected:
                active_channel_list.append(channel)
            else:
                # TODO: remove channel from active channel list if not already removed
                pass

    # TODO: end packet capture


if __name__ == "__main__":
    main()
