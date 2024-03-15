__version__ = "0.1.0"

# import numpy as np
import subprocess
import time
import pyshark


def get_channel_list():
    ''' This function returns a list of the WiFi channels that will be scanned in the order
    are scanned in a 5 second interval.'''

    #channels = {'TwoGHz':['1', '6', '11'], \
                #'FiveGHz1': ['36','40,'44','48'], \
                #'FiveGHz2':['149', '153', '157', '161'], \
                #'Scan_time':[0.5, 0.25]}
    channels = ['1', '6', '11','36','40','44','48','1', '6', '11','149', '153', '157', '161']
                               
    return channels

def main():

    #determining the interface name
    # Use MAC address on the back of the network card adapter
    MAC_addr = "00c0cab400dd"

    long_interface_name = f"wlx{MAC_addr}"
    short_interface_name = 'wlan1'

    print(f"Long Interface Name: {long_interface_name}")
    print(f"Short Interface Name: {short_interface_name}")
    
    #Check if monitor interface exists for long interface
    process_long = subprocess.Popen(['iwconfig', long_interface_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output_long, _ = process_long.communicate()

    # Run iwconfig for short interface
    process_short = subprocess.Popen(['iwconfig', short_interface_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output_short, _ = process_short.communicate()

    # Check if 'No such device' substring is present in both outputs
    if b'No such device' in output_long and b'No such device' in output_short:
        print(f"Didn't detect interface {long_interface_name} or {short_interface_name}")
        exit(1)

    # Default Wi-Fi channel to scan
    default_wifi_channel = 6

    # TODO: set up monitor mode
        # TODO: if dongle not connected, exit
        # Command to run
    command_long = f"sudo airmon-ng start {long_interface_name} 1 && airmon-ng check kill"
    command_short = f"sudo airmon-ng start {short_interface_name} 1 && airmon-ng check kill"

    #Run the command to start monitor mode
    try:
        subprocess.run(command_short, shell=True, check=True)
        subprocess.run(command_long, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        
    # Get list of Wi-Fi channels
    wifi_channel_list = get_channel_list()

    #active_channel_list = []

    initial_detection = True
    
    # This section loops through the WiFi Channels. It scans channels 1, 6, and 11 for 0.5
    # seconds each, scans 4  of the 5Ghz for 0.25 seconds each, returns to the 2.4 GHz channels
    # again for 0.5 seconds each, and then scans the last 4 5GHz channels for 0.25 seconds each.
    # This 5 second scanning pattern then repeats'''
    
    while initial_detection:
        
        for channel in wifi_channel_list:
            
            command = ["airmon-ng", "start", "wlan1mon", channel]
            # Run the command
            try:
                subprocess.run(command, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error: {e}")
                
            if channel == '1' or channel == '6' or channel == '11':
                time.sleep(0.5)
                #print('sleep for 5 s')
            else:
                time.sleep(0.25)
                #print('sleep for 2 s')

    # TODO: end packet capture


if __name__ == "__main__":
    main()
