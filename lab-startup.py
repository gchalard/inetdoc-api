#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import subprocess  # nosec B404
import sys

import yaml
from colorama import Fore, Style
from colorama import init as colorama_init

# Constants
MASTER_DIR = f"{os.environ.get('HOME')}/masters"
OVMF_CODE = "/usr/share/OVMF/OVMF_CODE_4M.secboot.fd"
OVMF_VARS = "/usr/share/OVMF/OVMF_VARS_4M.ms.fd"


# Use argparse to check if --help or -h is provided
# requires a yaml file
def check_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="YAML virtual machines declarative file to read")
    args = parser.parse_args()
    return args


# Read the yaml file and returns the data
def read_yaml(file):
    # check if the yaml file exists
    if not os.path.exists(file):
        print(f"Error: {file} not found!")
        sys.exit(1)

    # open the yaml file
    with open(file) as f:
        data = yaml.safe_load(f)
    return data


# Check if mandatory fields are present in the yaml file
def check_mandatory_fields(data):
    if "kvm" not in data:
        print(f"{Fore.LIGHTRED_EX}Error: kvm section is missing!{Style.RESET_ALL}")
        sys.exit(1)
    if "vms" not in data["kvm"]:
        print(f"{Fore.LIGHTRED_EX}Error: vms section is missing!{Style.RESET_ALL}")
        sys.exit(1)
    for vm in data["kvm"]["vms"]:
        if "name" not in vm:
            print(f"{Fore.LIGHTRED_EX}Error: name field is missing!{Style.RESET_ALL}")
            sys.exit(1)
        if "memory" not in vm:
            print(f"{Fore.LIGHTRED_EX}Error: memory field is missing!{Style.RESET_ALL}")
            sys.exit(1)
        if int(vm["memory"]) < 512:
            print(
                f"{Fore.LIGHTRED_EX}Error: memory field must be at least 512!{Style.RESET_ALL}"
            )
            sys.exit(1)
        if "tapnum" not in vm:
            print(f"{Fore.LIGHTRED_EX}Error: tapnum field is missing!{Style.RESET_ALL}")
            sys.exit(1)
        if "master_image" not in vm:
            print(
                f"{Fore.LIGHTRED_EX}Error: master_image field is missing!{Style.RESET_ALL}"
            )
            sys.exit(1)
        if "force_copy" not in vm:
            print(
                f"{Fore.LIGHTRED_EX}Error: force_copy field is missing!{Style.RESET_ALL}"
            )
            sys.exit(1)


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
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    tag = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", tap, "tag"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    switch = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "port-to-br", tap],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
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
    vm_image = vm_image + "." + get_image_format(master_image)
    if os.path.exists(vm_image) and not force:
        print(f"{Fore.LIGHTGREEN_EX}{vm_image} already exists!{Style.RESET_ALL}")
    else:
        master_image = f"{MASTER_DIR}/{master_image}"
        # Check if the master image exists
        if not os.path.exists(master_image):
            print(
                f"{Fore.LIGHTRED_EX}Error: {master_image} not found!{Style.RESET_ALL}"
            )
            sys.exit(1)
        else:
            print(
                f"{Fore.LIGHTBLUE_EX}Copying {master_image} to {vm_image}...{Style.RESET_ALL}"
            )
            subprocess.run(["cp", master_image, vm_image])  # nosec


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
        subprocess.run(["ln", "-sf", OVMF_CODE, "OVMF_CODE.fd"])  # nosec
    # Check OVMF vars file
    if not os.path.exists(f"{vm}_OVMF_VARS.fd"):
        print(f"{Fore.LIGHTBLUE_EX}Creating {vm}_OVMF_VARS.fd file...{Style.RESET_ALL}")
        subprocess.run(["cp", OVMF_VARS, f"{vm}_OVMF_VARS.fd"])  # nosec


# Check if the VM is running
def is_vm_running(vm):
    user_id = os.getuid()
    vm_pid = subprocess.run(
        ["pgrep", "-u", str(user_id), "-l", "-f", f"\-name\ {vm}"],
        stdout=subprocess.DEVNULL,
    )  # nosec
    if vm_pid.returncode != 0:
        return False
    else:
        return True


# Check if the tap interface is already in use
def is_tap_in_use(tapnum):
    tap_pid = subprocess.run(
        ["pgrep", "-f", f"=[t]ap{tapnum},"], stderr=subprocess.DEVNULL
    )  # nosec
    if tap_pid.returncode != 0:
        return False
    else:
        return True


# Build the qemu command
def build_qemu_cmd(vm):
    script = f"{MASTER_DIR}/scripts/ovs-startup.sh"
    vm_file = vm["name"] + "." + get_image_format(vm["master_image"])
    cmd = [script, vm_file, str(vm["memory"]), str(vm["tapnum"])]
    return cmd


# main function
def main():
    # Terminal color initialization
    colorama_init(autoreset=True)
    # Check if the yaml lab file is provided and read it
    arg = check_args()
    data = read_yaml(arg.file)
    check_mandatory_fields(data)
    # Loop through the virtual machines
    for vm in data["kvm"]["vms"]:
        image_format = get_image_format(vm["master_image"])
        if is_vm_running(vm["name"]):
            print(
                f"{Fore.LIGHTRED_EX}{vm['name']}.{image_format} is already running!{Style.RESET_ALL}"
            )
            sys.exit(1)
        if is_tap_in_use(vm["tapnum"]):
            print(
                f"{Fore.LIGHTRED_EX}tap{vm['tapnum']} is already in use!{Style.RESET_ALL}"
            )
            sys.exit(1)
        else:
            # Copy the master image to the VM image
            # If force_copy is True copy the image even if it exists
            copy_image(vm["master_image"], vm["name"], vm["force_copy"])
            # UEFI file and symlink check
            copy_uefi_files(vm["name"])
            qemu_cmd = build_qemu_cmd(vm)
            # print(qemu_cmd)
            print(f"{Fore.LIGHTBLUE_EX}Starting {vm['name']}...{Style.RESET_ALL}")
            proc = subprocess.run(qemu_cmd)  # nosec
            if proc.returncode != 0:
                print(
                    f"{Fore.LIGHTRED_EX}{vm['name']} failed to start!{Style.RESET_ALL}"
                )
                sys.exit(1)
            else:
                print(f"{Fore.LIGHTGREEN_EX}{vm['name']} started!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
