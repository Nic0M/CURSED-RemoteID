import calendar  # included
import csv  # included in base python, no need to install
import glob  # need to install seperately (use glob2 in pip)
import math  # included in base python
# import os  # included in base python
import time  # included in python

import boto3  # need to install sperately
import pyshark  # need to install seperately

# while true:
x = 1
while x < 2:
    if (
        glob.glob(
            'D:\\Engineering\\Senior_Projects_Example_Data'
            '\\full_packet_capture_*.pcapng',
        ) != []
    ):
        path = glob.glob(
            'D:\\Engineering\\Senior_Projects_Example_Data'
            '\\full_packet_capture_*.pcapng',
        )[0]
        pcap = pyshark.FileCapture(
            path, display_filter="opendroneid.message.location",
        )
        csvPath = path[:-6] + 'csv'
        with open(csvPath, 'w', newline='', encoding="utf-8") as file:
            writer = csv.writer(file)
            field = [
                "Access Address", "ID", "TimeStamp",
                "direction", "speed", "vspeed", "lat", "long",
            ]
            writer.writerow(field)
            for pkt in pcap:
                try:
                    access_address = pkt['BTLE'].get_field(
                        'btle.access_address',
                    )
                except KeyError:
                    access_address = pkt['WLAN'].get_field('wlan.sa_resolved')
                try:
                    temp = pcap[3].frame_info.time_utc[:3]
                    Month = str(list(calendar.month_abbr).index(temp))
                    Day = str(pcap[3].frame_info.time_utc[4:6])
                    Year = str(pcap[3].frame_info.time_utc[8:12])
                    B = pkt.frame_info.time_utc[13:15]
                    Minute = math.floor(
                        int(
                            pkt['OpenDroneID'].get_field(
                                'OpenDroneID.loc_timeStamp',
                            ),
                        ) / 10 / 60,
                    )
                    Second = math.floor(
                        int(
                            pkt['OpenDroneID'].get_field(
                                'OpenDroneID.loc_timeStamp',
                            ),
                        ) / 10 - (Minute * 60),
                    )
                    TimeStamp = Year + '-' + Month + '-' + Day + \
                        ' ' + B + ':' + str(Minute) + ':' + str(Second)
                    ID = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.basicID_id_asc',
                    )
                    direction = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_direction',
                    )
                    speed = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_speed',
                    )
                    vspeed = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_vspeed',
                    )
                    lat = pkt['OpenDroneID'].get_field('OpenDroneID.loc_lat')
                    lon = pkt['OpenDroneID'].get_field('OpenDroneID.loc_lon')
                except TypeError:
                    pass
                if (Minute < 60):
                    if str(ID).isascii():
                        writer.writerow(
                            [
                                access_address, ID, TimeStamp,
                                direction, speed, vspeed, lat, lon,
                            ],
                        )
                    else:
                        continue
        pcap.close()
        # os.remove(path)
        s3 = boto3.client(
            "s3",
            aws_access_key_id='',
            aws_secret_access_key='',
        )
        start_time = time.time_ns()
        s3.upload_file(csvPath, "cursed-remoteid-data", csvPath[-28:])
        end_time = time.time_ns()
        print(f'Elapsed upload time: {end_time - start_time:d} ns')
        # os.remove(csvPath)
    x = x + 1