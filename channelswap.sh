#!/bin/bash

# Get major and minor bash version e.g. 4.0
bash_version=$(bash --version | head -n 1 | grep -o '[0-9]\+\.[0-9]\+')

# Get the major version
major_version=${bash_version%%.*}

# Check if major version is greater or equal to 4
if [ "$major_version" -ge 4 ]; then
    echo "Bash version 4 or later is installed."
else
    echo 'Bash version is less than 4.'
    echo 'Exiting'
    exit 1
fi

# all_wifi_channels=( {1..14} {32..68..4} {96..144..4} {149..177..4} )
all_wifi_channels=(1 6 11 36 40 44 48 149 153 157 161)
# {1} {6} {11} {36} {40} {44} {48} {149} {153} {157} {161})

# Use MAC address on the back of the network card adapter
MAC_addr=00c0cab400dd

long_interface_name="wlx${MAC_addr}"
short_interface_name='wlan1mon'

# TODO:  Check if monitor interface exists
#if [ iwconfig "$long_interface_name" |& grep 'No such device' ] && [ iwconfig "$short_interface_name" |& grep 'No such device' ]; then
#    echo "Didn't detect interface $long_interface_name or $short_interface_name"
#    exit 1
#fi

# Ensure interface is started with short name
sudo airmon-ng start $long_interface_name 1 airmon-ng check kill
sudo airmon-ng start $short_interface_name 1 airmon-ng check kill

# Currently will overwrite file
tshark -i "$short_interface_name" -w 'outfile.pcap' -q &
# Allow tshark to initialize file
sleep 5

for channel in "${all_wifi_channels[@]}"
do
    echo "Scanning channel: $channel"
    sudo airmon-ng start wlan1mon "$channel"
    sleep $(5/11)
done

# Kill tshark process
kill -SIGKILL "$(pidof tshark)"
