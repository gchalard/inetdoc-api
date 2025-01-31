#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is part of https://inetdoc.net project
#
# It provides a declarative approach to virtual machine management on our type-2
# hypervisors. The virtual machines are defined in YAML files and this script
# calls the corresponding shell scripts to start them:
# - ovs-startup.sh for Linux and Windows virtual machines
# - ovs-iosxe.sh for Cisco C8000v virtual routers
#
# The shell scripts describe the virtual systems architecture:
# - Memory allocation
# - Storage device types and sizes
# - Network interface types and connections
# - GPU device types
#
# File: lab-startup.py
# Author: Philippe Latu
# Source: https://gitlab.inetdoc.net/labs/startup-scripts
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

import yaml
from colorama import Fore, Style
from colorama import init as colorama_init
from schema import And, Optional, Or, Schema, SchemaError, Use

# Constants
MASTER_DIR = Path.home() / "masters"
OVMF_CODE = Path("/usr/share/OVMF/OVMF_CODE_4M.secboot.fd")
OVMF_VARS = Path("/usr/share/OVMF/OVMF_VARS_4M.ms.fd")

DEFAULT_NETPLAN_FILE = "/etc/netplan/enp0s1.yaml"
CLOUD_INIT_NETPLAN_FILE = "/etc/netplan/50-cloud-init.yaml"


# Read the yaml template file and return its content as a string
def read_yaml_template(file):
    if not os.path.exists(file):
        return "Template file not found!"
    with open(file, "r") as f:
        return f.read()


# Use argparse to check if --help or -h is provided
# requires a yaml file
def check_args():
    yaml_template = read_yaml_template(f"{MASTER_DIR}/scripts/linux-lab-template.yaml")
    parser = argparse.ArgumentParser(
        description=f"YAML virtual machines declarative file to read.\n\nExample YAML template:\n\n{yaml_template}",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file", help="YAML virtual machines declarative file to read")
    args = parser.parse_args()
    return args


# Read the yaml file and returns the data
def read_yaml(file):
    # check if the yaml file exists
    if not os.path.exists(file):
        print(f"{Fore.LIGHTRED_EX}Error: {file} not found!{Style.RESET_ALL}")
        sys.exit(1)

    # open the yaml file
    with open(file, "r") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(
                f"{Fore.LIGHTRED_EX}Error: {file} is not a valid YAML file!{Style.RESET_ALL}"
            )
            print(exc)
            sys.exit(1)
    return data


# Check YAML declaration against the schema
def check_memory(value):
    if value < 512:
        raise SchemaError("Memory must be at least 512MB")
    return value


def validate_vm(vm):
    try:
        if vm["os"] in ["linux", "windows"]:
            linux_windows_schema.validate(vm)
        elif vm["os"] == "iosxe":
            iosxe_schema.validate(vm)
        else:
            raise SchemaError(f"Invalid OS type: {vm['os']}")
    except SchemaError as e:
        raise SchemaError(
            f"Error in VM '{vm.get('vm_name', 'unknown')}': {str(e)}"
        ) from e
    return vm


# Schema definitions
linux_windows_schema = Schema(
    {
        "vm_name": str,
        "os": Or("linux", "windows"),
        "master_image": str,
        "force_copy": bool,
        "memory": And(int, check_memory),
        "tapnum": int,
        Optional("cloud_init"): {
            Optional("force"): bool,
            Optional("netplan"): dict,
            str: object,  # Allow any other cloud-init keys
        },
        Optional("devices"): {
            Optional("storage"): [
                {"dev_name": str, "bus": Or("virtio", "scsi", "nvme"), "size": str}
            ]
        },
    }
)

iosxe_schema = Schema(
    {
        "vm_name": str,
        "os": "iosxe",
        "master_image": str,
        "force_copy": bool,
        "tapnumlist": [int],
    }
)

kvm_schema = Schema({"kvm": {"vms": [Use(validate_vm)]}})


def check_yaml_declaration(data):
    try:
        kvm_schema.validate(data)
    except SchemaError as e:
        print(f"{Fore.LIGHTRED_EX}Error: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


def check_unique_tapnums(data):
    tapnums = set()
    for vm in data["kvm"]["vms"]:
        if vm["os"] in ["linux", "windows"]:
            if vm["tapnum"] in tapnums:
                print(
                    f"{Fore.LIGHTRED_EX}Error: Duplicate tapnum {vm['tapnum']} found for {vm['vm_name']}{Style.RESET_ALL}"
                )
                sys.exit(1)
            tapnums.add(vm["tapnum"])
        elif vm["os"] == "iosxe":
            for tapnum in vm["tapnumlist"]:
                if tapnum in tapnums:
                    print(
                        f"{Fore.LIGHTRED_EX}Error: Duplicate tapnum {tapnum} found in tapnumlist for {vm['vm_name']}{Style.RESET_ALL}"
                    )
                    sys.exit(1)
                tapnums.add(tapnum)


# Get VM image format from master image extension
def get_image_format(image):
    if re.search(r"\.qcow2$", image):
        return "qcow2"
    elif re.search(r"\.raw$", image):
        return "raw"
    else:
        print(f"Error: {image} image format not supported!")
        sys.exit(1)


# Build mac address from tap interface number
def build_mac(tapnum):
    second_rightmost_byte = tapnum // 256
    rightmost_byte = tapnum % 256
    macaddress = f"b8:ad:ca:fe:{second_rightmost_byte:02x}:{rightmost_byte:02x}"
    return macaddress


# Build SVI name from tap interface number VLAN mode and VLAN ID
def build_svi_name(tapnum):
    tap = f"tap{tapnum}"
    vlan_mode = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", tap, "vlan_mode"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    tag = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", tap, "tag"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    switch = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "port-to-br", tap],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    if vlan_mode == "access":
        return f"vlan{tag}"
    else:
        return f"{switch}"


# Build IPv6 Link Local address from tap interface number
def build_ipv6_link_local(tapnum):
    svi = build_svi_name(tapnum)
    lladdress = f"fe80::baad:caff:fefe:{tapnum:x}%{svi}"
    return lladdress


# Copy the master image to the VM image if force_copy is True
def copy_image(master_image, vm_image, force):
    dst_file = vm_image + "." + get_image_format(master_image)
    if os.path.exists(dst_file) and not force:
        print(f"{Fore.LIGHTGREEN_EX}{dst_file} already exists!{Style.RESET_ALL}")
    else:
        src_file = f"{MASTER_DIR}/{master_image}"
        # Check if the master image file exists
        if not os.path.exists(src_file):
            print(f"{Fore.LIGHTRED_EX}Error: {src_file} not found!{Style.RESET_ALL}")
            sys.exit(1)
        else:
            print(
                f"{Fore.LIGHTBLUE_EX}Copying {src_file} to {dst_file}...{Style.RESET_ALL}",
                end="",
            )
            cp_result = subprocess.run(["cp", src_file, dst_file], check=True)  # nosec
            if cp_result.returncode == 0:
                print(f"{Fore.LIGHTBLUE_EX}done{Style.RESET_ALL}")
            else:
                print(f"{Fore.LIGHTRED_EX}failed!{Style.RESET_ALL}")
                sys.exit(1)


# Copy UEFI files to the VM directory
def copy_uefi_files(vm):
    # Check OVMF masters
    if not os.path.exists(OVMF_CODE):
        print(f"{Fore.LIGHTRED_EX}Error: {OVMF_CODE} not found!{Style.RESET_ALL}")
        sys.exit(1)
    if not os.path.exists(OVMF_VARS):
        print(f"{Fore.LIGHTRED_EX}Error: {OVMF_VARS} not found!{Style.RESET_ALL}")
        sys.exit(1)
    # Check OVMF code symlink
    if not os.path.exists("OVMF_CODE.fd") and not os.path.islink("OVMF_CODE.fd"):
        print(f"{Fore.LIGHTBLUE_EX}Creating OVMF_CODE.fd symlink...{Style.RESET_ALL}")
        subprocess.run(["ln", "-sf", OVMF_CODE, "OVMF_CODE.fd"], check=True)  # nosec
    # Check OVMF vars file
    if not os.path.exists(f"{vm}_OVMF_VARS.fd"):
        print(f"{Fore.LIGHTBLUE_EX}Creating {vm}_OVMF_VARS.fd file...{Style.RESET_ALL}")
        subprocess.run(["cp", OVMF_VARS, f"{vm}_OVMF_VARS.fd"], check=True)  # nosec


# Check if the VM is running
def is_vm_running(vm):
    user_id = os.getuid()
    vm_pid = subprocess.run(
        ["pgrep", "-u", str(user_id), "-l", "-f", f"-name {vm}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )  # nosec
    if vm_pid.returncode != 0:
        return False
    else:
        pid = vm_pid.stdout.decode("utf-8").split()[0]
        print(
            f"{Fore.LIGHTRED_EX}{vm} is already running with PID {pid}!{Style.RESET_ALL}"
        )
        return True


# Check if the tap interface is already in use
def is_tap_in_use(tapnum):
    tap_pid = subprocess.run(
        ["pgrep", "-f", f"=[t]ap{tapnum},"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )  # nosec
    if tap_pid.returncode != 0:
        return False
    else:
        pid = tap_pid.stdout.decode("utf-8").split()[0]
        print(
            f"{Fore.LIGHTRED_EX}tap{tapnum} is already in use by PID {pid}!{Style.RESET_ALL}"
        )
        return True


def build_device_command(store, dev_filename, dev_format, dev_id, dev_idx, dev_addr):
    if store["bus"] == "virtio":
        return [
            "-drive",
            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
            "-device",
            f"virtio-blk-pci,drive={dev_id},scsi=off,config-wce=off",
        ]
    elif store["bus"] == "scsi":
        return [
            "-device",
            f"virtio-scsi-pci,id=scsi{dev_idx},bus=pcie.0",
            "-drive",
            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
            "-device",
            f"scsi-hd,drive={dev_id},channel=0,scsi-id={dev_idx},lun={dev_addr}",
        ]
    elif store["bus"] == "nvme":
        return [
            "-drive",
            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
            "-device",
            f"nvme,drive={dev_id},serial=feedcafe{dev_idx}",
        ]
    return []


def create_image_if_not_exists(store):
    dev_filename = store["dev_name"]
    dev_format = get_image_format(dev_filename)
    dev_id = store["dev_name"].split(".")[0]
    if os.path.exists(dev_filename):
        print(f"{Fore.LIGHTGREEN_EX}{dev_id} already exists!{Style.RESET_ALL}")
    else:
        print(f"{Fore.LIGHTBLUE_EX}Creating {dev_id}...{Style.RESET_ALL}")
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-f",
                dev_format,
                "-o",
                "lazy_refcounts=on,extended_l2=on",
                dev_filename,
                store["size"],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )  # nosec


# Create cloud-init metadata and userdata files
def create_cloud_init_files(vm):
    if "cloud_init" not in vm:
        return None

    seed_img = f"{vm['vm_name']}-seed.img"

    # Check if seed.img should be created
    if not vm["cloud_init"].get("force_seed", False) and os.path.exists(seed_img):
        print(f"{Fore.LIGHTGREEN_EX}Using existing {seed_img}{Style.RESET_ALL}")
        return seed_img

    print(f"{Fore.LIGHTBLUE_EX}Creating {seed_img}...{Style.RESET_ALL}")
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create metadata file
        metadata = {"instance-id": vm["vm_name"], "local-hostname": vm["vm_name"]}

        # Add bootcmd to remove old netplan file
        if "netplan" in vm["cloud_init"]:
            if "bootcmd" not in vm["cloud_init"]:
                vm["cloud_init"]["bootcmd"] = []
            vm["cloud_init"]["bootcmd"].append(f"rm -f {DEFAULT_NETPLAN_FILE}")

            # Add write_files for new netplan config
            if "write_files" not in vm["cloud_init"]:
                vm["cloud_init"]["write_files"] = []
            vm["cloud_init"]["write_files"].append(
                {
                    "path": CLOUD_INIT_NETPLAN_FILE,
                    "content": yaml.dump(vm["cloud_init"]["netplan"]),
                }
            )

            # Add runcmd to apply new config
            if "runcmd" not in vm["cloud_init"]:
                vm["cloud_init"]["runcmd"] = []
            vm["cloud_init"]["runcmd"].extend(["netplan generate", "netplan apply"])

            # Remove netplan key as it's now processed
            del vm["cloud_init"]["netplan"]

        with open(f"{tmp_dir}/meta-data", "w") as f:
            yaml.dump(metadata, f)

        # Create user-data file
        with open(f"{tmp_dir}/user-data", "w") as f:
            f.write("#cloud-config\n")
            yaml.dump(vm["cloud_init"], f)

        # Create seed image
        try:
            subprocess.run(
                [
                    "cloud-localds",
                    seed_img,
                    f"{tmp_dir}/user-data",
                    f"{tmp_dir}/meta-data",
                ],
                capture_output=True,
                text=True,
                check=True,
            )  # nosec
        except FileNotFoundError:
            print(
                f"{Fore.LIGHTRED_EX}Error: cloud-localds command not found. Please install cloud-image-utils package.{Style.RESET_ALL}"
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(
                f"{Fore.LIGHTRED_EX}Error creating seed image: {e.stderr}{Style.RESET_ALL}"
            )
            sys.exit(1)

        return seed_img


# Build the qemu command
def build_qemu_cmd(vm):
    if vm["os"] == "linux":
        script = f"{MASTER_DIR}/scripts/ovs-startup.sh"
        vm_file = vm["vm_name"] + "." + get_image_format(vm["master_image"])
        cmd = [script, vm_file, str(vm["memory"]), str(vm["tapnum"]), "linux"]
        if "devices" in vm:
            dev_idx = 1
            dev_cmd = []
            if vm["devices"]["storage"]:
                for store in vm.get("devices", {}).get("storage", []):
                    create_image_if_not_exists(store)
                    dev_filename = store["dev_name"]
                    dev_format = get_image_format(dev_filename)
                    dev_id = f"drive{dev_idx}"
                    dev_addr = store.get("addr", 0)
                    dev_cmd.extend(
                        build_device_command(
                            store, dev_filename, dev_format, dev_id, dev_idx, dev_addr
                        )
                    )
                    dev_idx += 1
                cmd.extend(dev_cmd)
        seed_img = create_cloud_init_files(vm)
        if seed_img:
            cmd.extend(["-drive", f"file={seed_img},format=raw,if=virtio"])

    elif vm["os"] == "windows":
        script = f"{MASTER_DIR}/scripts/ovs-startup.sh"
        vm_file = vm["vm_name"] + "." + get_image_format(vm["master_image"])
        cmd = [script, vm_file, str(vm["memory"]), str(vm["tapnum"]), "windows"]
        if "devices" in vm:
            dev_idx = 1
            dev_cmd = []
            if vm["devices"]["storage"]:
                for store in vm.get("devices", {}).get("storage", []):
                    create_image_if_not_exists(store)
                    dev_filename = store["dev_name"]
                    dev_format = get_image_format(dev_filename)
                    dev_id = f"drive{dev_idx}"
                    dev_addr = store.get("addr", 0)
                    dev_cmd.extend(
                        build_device_command(
                            store, dev_filename, dev_format, dev_id, dev_idx, dev_addr
                        )
                    )
                    dev_idx += 1
                cmd.extend(dev_cmd)

    elif vm["os"] == "iosxe":
        script = f"{MASTER_DIR}/scripts/ovs-iosxe.sh"
        vm_file = vm["vm_name"] + "." + get_image_format(vm["master_image"])
        cmd = [script, vm_file]
        for intf in vm["tapnumlist"]:
            cmd.append(str(intf))
    return cmd


# main function
def main():
    # Terminal color initialization
    colorama_init(autoreset=True)
    # Check if the yaml lab file is provided and read it
    arg = check_args()
    data = read_yaml(arg.file)
    check_yaml_declaration(data)
    check_unique_tapnums(data)
    # Loop through the virtual machines
    for vm in data["kvm"]["vms"]:
        if not is_vm_running(vm["vm_name"]):
            if vm["os"] in ["linux", "windows"] and is_tap_in_use(vm["tapnum"]):
                sys.exit(1)
            elif vm["os"] == "iosxe":
                for intf in vm["tapnumlist"]:
                    if is_tap_in_use(intf):
                        sys.exit(1)
            # Copy the master image to the VM image
            # If force_copy is True copy the image even if it exists
            copy_image(vm["master_image"], vm["vm_name"], vm["force_copy"])
            # UEFI file and symlink check
            copy_uefi_files(vm["vm_name"])
            qemu_cmd = build_qemu_cmd(vm)
            print(f"{Fore.LIGHTBLUE_EX}Starting {vm['vm_name']}...{Style.RESET_ALL}")
            proc = subprocess.run(qemu_cmd)  # nosec
            if proc.returncode != 0:
                print(
                    f"{Fore.LIGHTRED_EX}{vm['vm_name']} failed to start!{Style.RESET_ALL}"
                )
                sys.exit(1)
            else:
                print(f"{Fore.LIGHTGREEN_EX}{vm['vm_name']} started!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
