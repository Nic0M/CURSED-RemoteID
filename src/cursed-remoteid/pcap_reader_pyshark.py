import pyshark #need to install seperately
import glob #need to install seperately (use glob2 in pip)
import csv #included in base python, no need to install
import os #included in base python
import logging #need to install sperately
import boto3 #need to install sperately
import math #included in base python
from botocore.exceptions import ClientError
import time #included in python


  
#while true:
x=1
while x<2:
    if(glob.glob('D:\\Engineering\\Senior_Projects_Example_Data\\full_packet_capture_*.pcapng')!=[]):
        path=glob.glob('D:\\Engineering\\Senior_Projects_Example_Data\\full_packet_capture_*.pcapng')[0]
        pcap=pyshark.FileCapture(path, display_filter="opendroneid.message.location")
        csvPath=path[:-6]+'csv'
        with open(csvPath, 'w', newline='',encoding="utf-8") as file:
            writer = csv.writer(file)
            field = ["Access Address","TimeStamp","ID","direction", "speed", "vspeed","lat","long"]
            writer.writerow(field)
            for pkt in pcap:
                try:
                    access_address=pkt['BTLE'].get_field('btle.access_address')
                except KeyError:
                    access_address=pkt['WLAN'].get_field('wlan.sa_resolved')
                try:
                    B = pkt.frame_info.time_utc[:15]
                    C=math.floor(int(pkt['OpenDroneID'].get_field('OpenDroneID.loc_timeStamp'))/10/60)
                    D=int(pkt['OpenDroneID'].get_field('OpenDroneID.loc_timeStamp'))/10-(C*60)
                    TimeStamp= B+':'+str(C)+':'+str(D)
                    ID=pkt['OpenDroneID'].get_field('OpenDroneID.basicID_id_asc')
                    direction=pkt['OpenDroneID'].get_field('OpenDroneID.loc_direction')
                    speed=pkt['OpenDroneID'].get_field('OpenDroneID.loc_speed')
                    vspeed=pkt['OpenDroneID'].get_field('OpenDroneID.loc_vspeed')
                    lat=pkt['OpenDroneID'].get_field('OpenDroneID.loc_lat')
                    lon=pkt['OpenDroneID'].get_field('OpenDroneID.loc_lon')
                except TypeError:
                    pass
                writer.writerow([access_address,TimeStamp,ID,direction,speed,vspeed,lat,lon])
        pcap.close()
        os.remove(path)
        s3 = boto3.client("s3",
                aws_access_key_id='GET FROM AWS',
                aws_secret_access_key='GET FROM AWS')
        start_time = time.time_ns()
        s3.upload_file(csvPath, "cursed-remoteid-data",csvPath[-28:])
        end_time = time.time_ns()
        print(f'Elapsed upload time: {end_time-start_time:d} ns')
        os.remove(csvPath)
    x=x+1
