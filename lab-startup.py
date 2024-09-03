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
        if "vm_name" not in vm:
            print(
                f"{Fore.LIGHTRED_EX}Error: vm_name field is missing!{Style.RESET_ALL}"
            )
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
    dst_file = vm_image + "." + get_image_format(master_image)
    if os.path.exists(dst_file) and not force:
        print(f"{Fore.LIGHTGREEN_EX}{dst_file} already exists!{Style.RESET_ALL}")
    else:
        src_file = f"{MASTER_DIR}/{master_image}"
        # Check if the master image file exists
        if not os.path.exists(src_file):
            print(
                f"{Fore.LIGHTRED_EX}Error: {src_file} not found!{Style.RESET_ALL}"
            )
            sys.exit(1)
        else:
            print(
                f"{Fore.LIGHTBLUE_EX}Copying {src_file} to {dst_file}...{Style.RESET_ALL}",
                end=""
            )
            cp_result = subprocess.run(["cp", src_file, dst_file])  # nosec
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
        subprocess.run(["ln", "-sf", OVMF_CODE, "OVMF_CODE.fd"])  # nosec
    # Check OVMF vars file
    if not os.path.exists(f"{vm}_OVMF_VARS.fd"):
        print(f"{Fore.LIGHTBLUE_EX}Creating {vm}_OVMF_VARS.fd file...{Style.RESET_ALL}")
        subprocess.run(["cp", OVMF_VARS, f"{vm}_OVMF_VARS.fd"])  # nosec


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


# Build the qemu command
def build_qemu_cmd(vm):
    script = f"{MASTER_DIR}/scripts/ovs-startup.sh"
    vm_file = vm["vm_name"] + "." + get_image_format(vm["master_image"])
    dev_cmd = []
    if "devices" in vm:
        dev_idx = 0
        if vm["devices"]["storage"]:
            for store in vm["devices"]["storage"]:
                if store["type"] == "disk":
                    dev_filename = store["dev_name"]
                    dev_format = get_image_format(dev_filename)
                    dev_id = store["dev_name"].split(".")[0]
                    if os.path.exists(store["dev_name"]):
                        print(
                            f"{Fore.LIGHTGREEN_EX}{dev_id} already exists!{Style.RESET_ALL}"
                        )
                    else:
                        print(
                            f"{Fore.LIGHTBLUE_EX}Creating {dev_id}...{Style.RESET_ALL}"
                        )
                        subprocess.run(
                            [
                                "qemu-img",
                                "create",
                                "-f",
                                dev_format,
                                "-o",
                                "lazy_refcounts=on,extended_l2=on",
                                store["dev_name"],
                                store["size"],
                            ],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )  # nosec
                    if store["bus"] == "virtio":
                        dev_cmd = dev_cmd + [
                            "-drive",
                            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
                            "-device",
                            f"virtio-blk-pci,drive={dev_id},scsi=off,config-wce=off",
                        ]
                    elif store["bus"] == "scsi":
                        dev_addr = dev_idx + 2
                        dev_cmd = dev_cmd + [
                            "-device",
                            f"virtio-scsi-pci,id=scsi{dev_idx},bus=pcie.0",
                            "-drive",
                            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
                            "-device",
                            f"scsi-hd,bus=scsi0.0,drive={dev_id},channel=0,scsi-id={dev_idx},lun={dev_addr}",
                        ]
                    elif store["bus"] == "nvme":
                        dev_cmd = dev_cmd + [
                            "-drive",
                            f"file={dev_filename},format={dev_format},media=disk,if=none,id={dev_id},cache=writeback",
                            "-device",
                            f"nvme,drive={dev_id},serial=feedcafe{dev_idx}",
                        ]
        dev_idx += 1
    cmd = [script, vm_file, str(vm["memory"]), str(vm["tapnum"])]
    if dev_cmd:
        cmd = cmd + dev_cmd
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
        if not is_vm_running(vm["vm_name"]) and not is_tap_in_use(vm["tapnum"]):
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
