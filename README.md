# CURSED-RemoteID
CU Receiver System for Enforcing Drones via Remote ID

# Installation

## Create virtual environment
Change to home directory, or whatever directory is desired.
```shell
cd
```
Install python3 virtual environment, you can skip this step if it is already installed.
```shell
sudo apt install python3-venv
```
Create a virtual environment
```shell
python3 -m venv remote-id-venv
```
Activate the virtual environment
```shell
source remote-id-venv/bin/activate
```

## Clone repository
Clone the repository
```shell
git clone https://github.com/Nic0M/CURSED-RemoteID.git
```
Move into the repository
```shell
cd CURSED-RemoteID
```
```shell
pip install -r requirements.txt
```

## Add AWS Credentials
Create the directory which boto3 will search for AWS credentials in
```shell
mkdir -p ~/.aws && cd ~/.aws
```
Create the credentials file:
```shell
touch credentials && touch config
```
With your favorite text editor, add your AWS secret access key.
> credentials
> ```editorconfig
> [default]
> aws_access_key_id = <key id goes here>
> aws_secret_access_key = <secret access key goes here>
> ```
Make sure the region matches the region of the S3 bucket being uploaded to.
> config
> ```editorconfig
> [default]
> region = us-east-2
> ```

## Install utilities
Install the command-line version of Wireshark `tshark`.
```shell
sudo apt install tshark
```
Now copy the Open Drone ID .lua script from the git repository to the Wireshark plugins folder.
```shell
cp ~/CURSED-RemoteID/opendroneid-dissector.lua ~/.local/lib/wireshark/plugins/
```
Install `iw` if not already installed with your Linux distribution.
```shell
sudo apt install iw
```
Install aircrack-ng, we specifically need `airmon-ng` from it.
```shell
sudo apt install aircrack-ng
```

## Running the script
Ensure the USB network card is connected.
```shell
cd ~/CURSED-RemoteID
```
Make sure the virtual environment is activated and you have sudo permissions.
```shell
python src/cursed_remote_id/
```
Set the `-v` or `--verbose` flag to show info messages to the console.
```shell
python src/cursed_remote_id/ -v
```
