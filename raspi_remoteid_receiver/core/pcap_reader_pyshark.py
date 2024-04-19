import pyshark  # need to install seperately
import glob  # need to install seperately (use glob2 in pip)
import csv  # included in base python, no need to install
import os  # included in base python
import logging  # need to install sperately
import boto3  # need to install sperately
import math  # included in base python
from botocore.exceptions import ClientError
import time  # included in python
import calendar  # included


while true:
    if (glob.glob('D:\\Engineering\\Senior_Projects_Example_Data\\full_packet_capture_*.pcapng') != []):
        path = glob.glob(
            'D:\\Engineering\\Senior_Projects_Example_Data\\full_packet_capture_*.pcapng')[0]
        pcap = pyshark.FileCapture(
            path, display_filter="opendroneid.message.location")
        csvPath = path[:-6] + 'csv'
        with open(csvPath, 'w', newline='', encoding="utf-8") as file:
            writer = csv.writer(file)
            field = [
                "Source Address",
                "Unique ID",
                "Timestamp",
                "Heading",
                "Ground Speed",
                "Vertical Speed",
                "Latitude",
                "Longitude",
                "Barometric Altitude",
                "Geodetic Altitude",
                "Height",
                "Horizontal Accuracy",
                "Geodetic Vertical Accuracy",
                "Barometric Altitude Accuracy",
                "Speed Accuracy"]
            writer.writerow(field)
            for pkt in pcap:
                try:
                    access_address = pkt['BTLE'].get_field(
                        'btle.access_address')
                except KeyError:
                    access_address = pkt['WLAN'].get_field('wlan.sa_resolved')
                try:
                    temp = pcap[3].frame_info.time_utc[:3]
                    Month = str(list(calendar.month_abbr).index(temp))
                    Day = str(pcap[3].frame_info.time_utc[4:6])
                    Year = str(pcap[3].frame_info.time_utc[8:12])
                    B = pkt.frame_info.time_utc[13:15]
                    Minute = math.floor(int(pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_timeStamp')) / 10 / 60)
                    Second = math.floor(int(pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_timeStamp')) / 10 - (Minute * 60))
                    TimeStamp = Year + '-' + Month + '-' + Day + \
                        ' ' + B + ':' + str(Minute) + ':' + str(Second)
                    ID = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.basicID_id_asc')
                    direction = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_direction')
                    speed = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_speed')
                    vspeed = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_vspeed')
                    lat = pkt['OpenDroneID'].get_field('OpenDroneID.loc_lat')
                    lon = pkt['OpenDroneID'].get_field('OpenDroneID.loc_lon')
                    pressALT = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_pressAlt')
                    geoALT = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_geoAlt')
                    height = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_height')
                    Haccuracy = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_hAccuracy')
                    Vaccuracy = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_vAccuracy')
                    Baroaccuracy = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_baroccuracy')
                    Speedaccuracy = pkt['OpenDroneID'].get_field(
                        'OpenDroneID.loc_speedAccuracy')
                except TypeError:
                    pass
                if (Minute < 60):
                    if str(ID).isascii():
                        writer.writerow([access_address,
                                         ID,
                                         TimeStamp,
                                         direction,
                                         speed,
                                         vspeed,
                                         lat,
                                         lon,
                                         pressALT,
                                         geoALT,
                                         height,
                                         Haccuracy,
                                         Vaccuracy,
                                         Baroaccuracy,
                                         Speedaccuracy])
                    else:
                        continue
        pcap.close()
        os.remove(path)
        s3 = boto3.client("s3",
                          aws_access_key_id='',
                          aws_secret_access_key='')
        start_time = time.time_ns()
        s3.upload_file(csvPath, "cursed-remoteid-data", csvPath[-28:])
        end_time = time.time_ns()
        # print(f'Elapsed upload time: {end_time-start_time:d} ns')
        os.remove(csvPath)
