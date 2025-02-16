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
from enum import Enum
from pathlib import Path

import yaml
from colorama import Fore, Style
from colorama import init as colorama_init
from schema import And, Optional, Or, Schema, SchemaError

# Constants
MASTER_DIR = Path.home() / "masters"
TEMPLATE_DIR = Path.joinpath(MASTER_DIR, "scripts/templates")
OVMF_CODE = Path("/usr/share/OVMF/OVMF_CODE_4M.secboot.fd")
OVMF_VARS = Path("/usr/share/OVMF/OVMF_VARS_4M.ms.fd")

CLOUD_INIT_NETPLAN_FILE = "/etc/netplan/50-cloud-init.yaml"


# Enum for console print colors
class ConsoleAttr(Enum):
    SUCCESS = "success"
    INFO = "info"
    ERROR = "error"


def console_print(msg, attr) -> None:
    """Prints a message to the console its attribute: success, info or error.

    This function prints a message to the console with color attributes. The
    message is printed in the specified color and the color attributes are reset
    at the end of the message.

    Args:
        msg (str): Message to print.
        attr (str): success, info or error.

    Example:
        >>> console_print("Hello, World!", success)
    """
    if attr == ConsoleAttr.SUCCESS:
        print(f"{Fore.LIGHTGREEN_EX}{msg}{Style.RESET_ALL}")
    elif attr == ConsoleAttr.INFO:
        print(f"{Fore.LIGHTBLUE_EX}{msg}{Style.RESET_ALL}")
    elif attr == ConsoleAttr.ERROR:
        print(f"{Fore.LIGHTRED_EX}{msg}{Style.RESET_ALL}")


def run_subprocess(
    cmd, error_msg, capture_output=False, check=True
) -> subprocess.CompletedProcess:
    """
    Executes a subprocess command with standardised error handling and real-time output display.

    Args:
        cmd (list): Command to execute.
        error_msg (str): Error message to display on failure.
        capture_output (bool): If True, capture output (default False to display output in real time).
        check (bool): Throw an exception on error (default True).

    Returns:
        subprocess.CompletedProcess: Result of execution.

    Raises:
        SystemExit: On execution error.
    """
    try:
        if capture_output:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=check
            )  # nosec
        else:
            result = subprocess.run(
                cmd, stdout=sys.stdout, stderr=sys.stderr, text=True, check=check
            )  # nosec
        return result
    except subprocess.CalledProcessError as e:
        console_print(f"{error_msg}: {e.stderr}", ConsoleAttr.ERROR)
        sys.exit(1)
    except FileNotFoundError:
        console_print(f"Commande non trouvée : {cmd[0]}", ConsoleAttr.ERROR)
        sys.exit(1)


def read_yaml_template(file) -> str:
    """Reads and returns the contents of a YAML template file.

    This function checks the existence of the file and returns its contents as a
    string. Template files are used as examples for
    the command's online help.

    Args:
        file (str): Full path to the YAML template file.

    Returns:
        str: Contents of the template file if found, otherwise ‘Template file not found!’.

    Example:
        >>> template_file = f"{TEMPLATE_DIR}/linux-lab.yaml’
        >>> content = read_yaml_template(template_file)
    """
    if not os.path.exists(file):
        return "Template file not found!"
    try:
        with open(file, "r") as f:
            return f.read()
    except Exception as e:
        console_print(f"Error: {file} could not be read!", ConsoleAttr.ERROR)
        print(e)
        sys.exit(1)


def check_args() -> argparse.Namespace:
    """Parse and validate command line arguments.

    This function reads the template YAML file and uses it as an example in the
    command help (--help or -h). It requires exactly one argument which is the
    path to a YAML file containing virtual machine declarations.

    Returns:
        argparse.Namespace: Object containing the validated command line arguments.
            file (str): Path to YAML configuration file to read.

    Example:
        >>> args = check_args()
        >>> data = read_yaml(args.file)

    Raises:
        SystemExit: If required argument is missing or invalid.
    """
    template_file = f"{TEMPLATE_DIR}/linux-lab.yaml"
    yaml_template = read_yaml_template(template_file)
    parser = argparse.ArgumentParser(
        description=f"YAML virtual machines declarative file to read.\n\nExample YAML template:\n\n{yaml_template}",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file", help="YAML virtual machines declarative file to read")
    args = parser.parse_args()
    return args


def read_yaml(file) -> dict:
    """Read and return the content of a YAML configuration file.

    This function checks the file existence and returns its content as a Python
    dictionary. The YAML file must contain valid virtual machine declarations.

    Args:
        file (str): Path to the YAML configuration file.

    Returns:
        dict: YAML file content as a Python dictionary.
            Example:
            {
                'kvm': {
                    'vms': [{
                        'vm_name': 'vm1',
                        'os': 'linux',
                        ...
                    }]
                }
            }

    Raises:
        SystemExit: If file doesn't exist or isn't valid YAML.

    Example:
        >>> data = read_yaml("templates/linux-lab.yaml")
        >>> vms = data["kvm"]["vms"]
    """
    # check if the yaml file exists
    if not os.path.exists(file):
        console_print(f"Error: {file} not found!", ConsoleAttr.ERROR)
        sys.exit(1)

    # open the yaml file
    try:
        with open(file, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        console_print(f"Error: {file} is not a valid YAML file!", ConsoleAttr.ERROR)
        print(e)
        sys.exit(1)
    except Exception as e:
        console_print(f"Error: {file} could not be read!", ConsoleAttr.ERROR)
        print(e)
        sys.exit(1)
    return data


def check_memory(value) -> int:
    """Check if the virtual machine memory allocation is valid.

    This function verifies that the memory value is greater than or equal to 512MB,
    which is the minimum required for virtual machine operation.

    Args:
        value (int): Memory size in MB to validate.

    Returns:
        int: The validated memory value.

    Raises:
        SchemaError: If memory value is less than 512MB.

    Example:
        >>> check_memory(1024)
        1024
        >>> check_memory(256)  # raises SchemaError
    """
    if value < 512:
        raise SchemaError("Memory must be at least 512MB")
    return value


# Schema definitions for YAML validation
linux_schema = Schema(
    {
        "vm_name": str,
        "os": "linux",
        "master_image": str,
        "force_copy": bool,
        "memory": And(int, lambda n: n >= 512),
        "tapnum": int,
        Optional("cloud_init"): {
            Optional("force_seed"): bool,
            Optional("users"): [
                {"name": str, "sudo": str, Optional("ssh_authorized_keys"): [str]}
            ],
            Optional("hostname"): str,
            Optional("packages"): [str],
            Optional("netplan"): dict,
            Optional("write_files"): [
                {"path": str, "content": str, Optional("append"): bool}
            ],
            Optional("runcmd"): [Or(str, [str])],
        },
        Optional("devices"): dict,
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

windows_schema = Schema(
    {
        "vm_name": str,
        "os": "windows",
        "master_image": str,
        "force_copy": bool,
        "memory": And(int, lambda n: n >= 512),
        "tapnum": int,
        Optional("devices"): dict,
    }
)


def check_yaml_declaration(vm):
    """Validate virtual machine YAML declaration against predefined schemas.

    This function validates the virtual machine declaration against the appropriate
    schema based on the OS type (linux, windows, or iosxe). Each schema defines
    the required and optional fields for that OS type.

    Args:
        vm (dict): Virtual machine declaration to validate.
            Example:
            {
                'vm_name': 'vm1',
                'os': 'linux',
                'master_image': 'debian-testing-amd64.qcow2',
                'force_copy': False,
                'memory': 2048,
                'tapnum': 1
            }

    Raises:
        SchemaError: If VM declaration doesn't match the schema.
        SystemExit: If schema validation fails.

    Example:
        >>> vm = {'vm_name': 'vm1', 'os': 'linux', ...}
        >>> check_yaml_declaration(vm)
    """
    try:
        if vm["os"] == "linux":
            linux_schema.validate(vm)
        elif vm["os"] == "windows":
            windows_schema.validate(vm)
        elif vm["os"] == "iosxe":
            iosxe_schema.validate(vm)
        else:
            raise SchemaError(f"Invalid OS type: {vm['os']}")
    except SchemaError as e:
        console_print(
            f"Error in VM '{vm.get('vm_name', 'unknown')}': {str(e)}", ConsoleAttr.ERROR
        )
        sys.exit(1)


def check_unique_tapnums(data):
    """Check for duplicate tap interface numbers in virtual machine declarations.

    This function ensures that tap interface numbers are unique across all virtual
    machines in the configuration. For Linux and Windows VMs, it checks the 'tapnum'
    field. For IOS XE VMs, it checks all numbers in the 'tapnumlist' field.

    Args:
        data (dict): YAML configuration dictionary containing VM declarations.
            Example:
            {
                'kvm': {
                    'vms': [
                        {
                            'vm_name': 'vm1',
                            'os': 'linux',
                            'tapnum': 1
                        },
                        {
                            'vm_name': 'rtr1',
                            'os': 'iosxe',
                            'tapnumlist': [2, 3, 4]
                        }
                    ]
                }
            }

    Raises:
        SystemExit: If duplicate tap interface numbers are found.

    Example:
        >>> data = read_yaml("templates/lab.yaml")
        >>> check_unique_tapnums(data)
    """
    tapnums = set()
    for vm in data["kvm"]["vms"]:
        if vm["os"] in ["linux", "windows"]:
            if vm["tapnum"] in tapnums:
                console_print(
                    f"Error: Duplicate tapnum {vm['tapnum']} found for {vm['vm_name']}",
                    ConsoleAttr.ERROR,
                )
                sys.exit(1)
            tapnums.add(vm["tapnum"])
        elif vm["os"] == "iosxe":
            for tapnum in vm["tapnumlist"]:
                if tapnum in tapnums:
                    console_print(
                        f"Error: Duplicate tapnum {tapnum} found for {vm['vm_name']}",
                        ConsoleAttr.ERROR,
                    )
                    sys.exit(1)
                tapnums.add(tapnum)


def get_image_format(image) -> str:
    """Get the image format from the master image filename extension.

    This function checks if the image file has a supported extension (.qcow2 or .raw)
    and returns the corresponding format string required by QEMU.

    Args:
        image (str): Name or path of the image file to check.
            Example: debian-stable-amd64.qcow2

    Returns:
        str: Image format ('qcow2' or 'raw')

    Raises:
        SystemExit: If the image extension is not supported.

    Example:
        >>> get_image_format("debian-stable-amd64.qcow2")
        'qcow2'
        >>> get_image_format("win11.raw")
        'raw'
    """
    if re.search(r"\.qcow2$", image):
        return "qcow2"
    elif re.search(r"\.raw$", image):
        return "raw"
    else:
        console_print(f"Error: {image} image format not supported!", ConsoleAttr.ERROR)
        sys.exit(1)


def build_mac(tapnum) -> str:
    """Build a MAC address from a tap interface number.

    This function generates a unique MAC address for virtual machine network interfaces
    using a fixed prefix (b8:ad:ca:fe) and the tap interface number. The tap number
    is split into two bytes to form the last two octets of the MAC address.

    Args:
        tapnum (int): Tap interface number (0-65535).

    Returns:
        str: MAC address in the format 'b8:ad:ca:fe:xx:yy' where:
            - xx is the second rightmost byte of tapnum in hex
            - yy is the rightmost byte of tapnum in hex

    Example:
        >>> build_mac(1)
        'b8:ad:ca:fe:00:01'
        >>> build_mac(256)
        'b8:ad:ca:fe:01:00'
        >>> build_mac(257)
        'b8:ad:ca:fe:01:01'
    """
    second_rightmost_byte = tapnum // 256
    rightmost_byte = tapnum % 256
    macaddress = f"b8:ad:ca:fe:{second_rightmost_byte:02x}:{rightmost_byte:02x}"
    return macaddress


def build_svi_name(tapnum) -> str:
    """Build a switched virtual interface name based on tap interface properties.

    This function queries Open vSwitch to get the VLAN mode, tag and switch name
    associated with a tap interface. It then builds the appropriate interface name:
    - For access ports: vlan<tag> (e.g. vlan10)
    - For trunk ports: <switch_name> (e.g. dsw-host)

    Args:
        tapnum (int): Tap interface number to query.

    Returns:
        str: Generated interface name based on port configuration.

    Raises:
        subprocess.CalledProcessError: If ovs-vsctl commands fail.
        SystemExit: If unable to get port configuration.

    Example:
        >>> build_svi_name(20)  # For access port with tag 10
        'vlan10'
        >>> build_svi_name(21)  # For trunk port on switch dsw-host
        'dsw-host'
    """
    tap = f"tap{tapnum}"
    vlan_mode = run_subprocess(
        ["sudo", "ovs-vsctl", "get", "port", tap, "vlan_mode"]
    ).stdout.strip()
    tag = run_subprocess(
        ["sudo", "ovs-vsctl", "get", "port", tap, "tag"]
    ).stdout.strip()
    switch = run_subprocess(["sudo", "ovs-vsctl", "port-to-br", tap]).stdout.strip()
    if vlan_mode == "access":
        return f"vlan{tag}"
    else:
        return f"{switch}"


def build_ipv6_link_local(tapnum) -> str:
    """Build an IPv6 Link-Local address from a tap interface number.

    This function generates a unique IPv6 Link-Local address for virtual machine
    network interfaces using a fixed prefix (fe80::baad:caff:fefe) and the tap
    interface number. The interface name is appended as a scope identifier.

    Args:
        tapnum (int): Tap interface number used to generate the address.

    Returns:
        str: IPv6 Link-Local address in the format 'fe80::baad:caff:fefe:xx%iface'
            where:
            - xx is the tap number in hex
            - iface is either vlan<tag> for access ports or switch name for trunk ports

    Example:
        >>> build_ipv6_link_local(20)  # For access port with tag 10
        'fe80::baad:caff:fefe:14%vlan10'
        >>> build_ipv6_link_local(21)  # For trunk port on switch dsw-host
        'fe80::baad:caff:fefe:15%dsw-host'
    """
    svi = build_svi_name(tapnum)
    lladdress = f"fe80::baad:caff:fefe:{tapnum:x}%{svi}"
    return lladdress


def copy_image(master_image, vm_image, force) -> None:
    """Copy a master image to create a new virtual machine image.

    This function copies a master image from the masters directory to create a new
    virtual machine image. The destination filename is built from the VM name and
    the source image format (qcow2 or raw).

    Args:
        master_image (str): Source image filename in masters directory.
        vm_image (str): Destination VM name without extension.
        force (bool): If True, overwrite existing destination file.

    Raises:
        SystemExit: If source file doesn't exist or copy operation fails.

    Example:
        >>> copy_image("debian-stable-amd64.qcow2", "vm1", False)
        # Creates vm1.qcow2 if it doesn't exist
        >>> copy_image("win11.raw", "win-test", True)
        # Creates/overwrites win-test.raw
    """
    dst_file = vm_image + "." + get_image_format(master_image)
    if os.path.exists(dst_file) and not force:
        console_print(f"{dst_file} already exists!", ConsoleAttr.SUCCESS)
    else:
        src_file = f"{MASTER_DIR}/{master_image}"
        # Check if the master image file exists
        if not os.path.exists(src_file):
            console_print(f"Error: {src_file} not found!", ConsoleAttr.ERROR)
            sys.exit(1)
        else:
            console_print(f"Copying {src_file} to {dst_file}...", ConsoleAttr.INFO)
            cp_result = run_subprocess(
                ["cp", src_file, dst_file], "Error: copy failed!"
            )
            if cp_result.returncode == 0:
                console_print("done.", ConsoleAttr.SUCCESS)


def copy_uefi_files(vm) -> None:
    """Copy and configure UEFI files for virtual machine UEFI boot.

    This function checks for required OVMF files existence and sets up UEFI boot
    environment for a virtual machine:
    - Checks existence of master OVMF code and variables files
    - Creates a symlink to the OVMF code file if needed
    - Creates a VM-specific copy of OVMF variables file if needed

    Args:
        vm (str): Virtual machine name used to create OVMF variables file.

    Raises:
        SystemExit: If OVMF master files are not found or copy operations fail.

    Example:
        >>> copy_uefi_files("vm1")
        # Creates vm1_OVMF_VARS.fd and OVMF_CODE.fd symlink if needed
    """
    # Check OVMF masters
    if not os.path.exists(OVMF_CODE):
        console_print(f"Error: {OVMF_CODE} not found!", ConsoleAttr.ERROR)
        sys.exit(1)
    if not os.path.exists(OVMF_VARS):
        console_print(f"Error: {OVMF_VARS} not found!", ConsoleAttr.ERROR)
        sys.exit(1)
    # Check OVMF code symlink
    if not os.path.exists("OVMF_CODE.fd") and not os.path.islink("OVMF_CODE.fd"):
        console_print("Creating OVMF_CODE.fd symlink...", ConsoleAttr.INFO)
        run_subprocess(
            ["ln", "-sf", OVMF_CODE, "OVMF_CODE.fd"], "Error: symlink failed!"
        )
    # Check OVMF vars file
    if not os.path.exists(f"{vm}_OVMF_VARS.fd"):
        console_print(f"Creating {vm}_OVMF_VARS.fd file...", ConsoleAttr.INFO)
        run_subprocess(["cp", OVMF_VARS, f"{vm}_OVMF_VARS.fd"], "Error: copy failed!")


def is_vm_running(vm) -> bool:
    """Check if a virtual machine is already running with the same name.

    This function searches for a QEMU process with the given VM name in the
    current user's process list. It uses the pgrep command to find processes
    matching '-name <vm>' in their command line.

    Args:
        vm (str): Name of the virtual machine to check.

    Returns:
        bool: True if VM is running, False otherwise.
            Also prints error message with PID if VM is found running.

    Example:
        >>> is_vm_running("vm1")
        False
        >>> is_vm_running("vm2")
        'vm2 is already running with PID 1234!'
        True
    """
    user_id = os.getuid()
    vm_pid = run_subprocess(
        ["pgrep", "-u", str(user_id), "-l", "-f", f"-name {vm}"],
        f"Error: failed to check if {vm} is running!",
        capture_output=True,
        check=False,
    )
    if vm_pid.returncode != 0:
        return False
    else:
        pid = vm_pid.stdout.decode("utf-8").split()[0]
        console_print(f"{vm} is already running with PID {pid}!", ConsoleAttr.ERROR)
        return True


def is_tap_in_use(tapnum) -> bool:
    """Check if a tap interface is already being used by a QEMU process.

    This function searches for QEMU processes using a specific tap interface number
    in their command line arguments. It uses the pgrep command to find processes
    with 'tap<number>' in their arguments.

    Args:
        tapnum (int): Tap interface number to check.

    Returns:
        bool: True if tap interface is in use, False otherwise.
            Also prints error message with PID if tap is found in use.

    Example:
        >>> is_tap_in_use(1)
        False
        >>> is_tap_in_use(2)
        'tap2 is already in use by PID 1234!'
        True
    """
    tap_pid = run_subprocess(
        ["pgrep", "-f", f"=[t]ap{tapnum},"],
        f"Error: interface tap{tapnum} is already in use!",
        capture_output=True,
        check=False,
    )
    if tap_pid.returncode != 0:
        return False
    else:
        pid = tap_pid.stdout.split()[0]
        console_print(f"tap{tapnum} is already in use by PID {pid}!", ConsoleAttr.ERROR)
        return True


def build_device_cmd(
    store, dev_filename, dev_format, dev_id, dev_idx, dev_addr
) -> list:
    """Build QEMU command arguments for storage device attachment.

    This function generates the appropriate QEMU command line arguments for
    attaching a storage device based on the bus type (virtio, scsi, or nvme).
    Each bus type has its specific configuration parameters.

    Args:
        store (dict): Storage device configuration dictionary containing bus type.
        dev_filename (str): Path to the device image file.
        dev_format (str): Format of the device image (qcow2 or raw).
        dev_id (str): Unique identifier for the device.
        dev_idx (int): Device index number used in bus addressing.
        dev_addr (int): Device address used in SCSI bus configuration.

    Returns:
        list: QEMU command arguments for device attachment.
            Examples:
            - For virtio: ['-drive', 'file=disk1.qcow2,...', '-device', 'virtio-blk-pci,...']
            - For SCSI: ['-device', 'virtio-scsi-pci,...', '-drive', 'file=disk1.qcow2,...']
            - For NVMe: ['-drive', 'file=disk1.qcow2,...', '-device', 'nvme,...']
            - Empty list if bus type is not supported

    Example:
        >>> store = {"bus": "virtio"}
        >>> build_device_cmd(store, "disk1.qcow2", "qcow2", "drive1", 1, 0)
        ['-drive', 'file=disk1.qcow2,...', '-device', 'virtio-blk-pci,...']
    """
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


def create_device_image_file(store) -> None:
    """Create a new QEMU disk image file for storage device if it doesn't exist.

    This function creates a new disk image file with the specified format and size
    using qemu-img. The image is created with optimized settings for QEMU:
    - lazy_refcounts for better performance
    - extended_l2 for larger block size support

    Args:
        store (dict): Storage device configuration dictionary containing:
            dev_name (str): Image filename to create
            size (str): Image size (e.g. "20G")
            bus (str): Bus type (virtio, scsi, nvme)

    Raises:
        SystemExit: If image creation fails.

    Example:
        >>> store = {
        ...     "dev_name": "disk1.qcow2",
        ...     "size": "32G",
        ...     "bus": "virtio"
        ... }
        >>> create_device_image_file(store)
        # Creates disk1.qcow2 if it doesn't exist
    """
    dev_filename = store["dev_name"]
    dev_format = get_image_format(dev_filename)
    dev_id = store["dev_name"].split(".")[0]
    if os.path.exists(dev_filename):
        console_print(f"{dev_id} already exists!", ConsoleAttr.SUCCESS)
    else:
        console_print(f"Creating {dev_id}...", ConsoleAttr.INFO)
        run_subprocess(
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
            f"Error: Failed to create {dev_id}!",
        )
        if os.path.exists(dev_filename):
            console_print("done.", ConsoleAttr.SUCCESS)
        else:
            console_print("failed!", ConsoleAttr.ERROR)
            sys.exit(1)


# Create cloud-init VRF specific entries
# Override the default systemd-networkd-wait-online as VM startup gets stuck
# waiting for the default interface to come up.
# The VRF interface is the one to wait for.
networkd_wait_online_override_content = """\
[Service]
ExecStart=
ExecStart=/lib/systemd/systemd-networkd-wait-online -o routable -i VRF_INTERFACE"""

networkd_wait_online_override_file = (
    "/etc/systemd/system/systemd-networkd-wait-online.service.d/override.conf"
)

# Create a dedicated SSH service for the VRF as this is the automation and
# management interface
vrf_ssh_service_content = """\
[Unit]
Description=OpenBSD Secure Shell server
Documentation=man:sshd(8) man:sshd_config(5)
After=network.target nss-user-lookup.target auditd.service
ConditionPathExists=!/etc/ssh/sshd_not_to_be_run

[Service]
EnvironmentFile=-/etc/default/ssh
ExecStartPre=/usr/sbin/ip vrf exec mgmt-vrf mkdir -p /run/sshd
ExecStartPre=/usr/sbin/ip vrf exec mgmt-vrf chmod 0755 /run/sshd
ExecStartPre=/usr/sbin/ip vrf exec mgmt-vrf /usr/sbin/sshd -t
ExecStart=/usr/sbin/ip vrf exec mgmt-vrf    /usr/sbin/sshd
ExecReload=/usr/sbin/ip vrf exec mgmt-vrf   /usr/sbin/sshd -t
ExecReload=/bin/kill -HUP ${MAINPID}
KillMode=process
Restart=on-failure
RestartPreventExitStatus=255
Type=notify
RuntimeDirectory=sshd
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
Alias=vrf-sshd.service"""

vrf_ssh_service_file = "/etc/systemd/system/vrf-ssh.service"


def create_vrf_userdata(vm, userdata) -> None:
    """Create VRF configuration in cloud-init userdata.

    This function configures VRF-specific settings in cloud-init userdata:
    - Configures systemd-networkd-wait-online to wait for VRF interface
    - Sets up a dedicated SSH service running in the VRF context
    - Configures DNS resolution for VRF as systemd-resolved is not VRF aware

    Args:
        vm (dict): Virtual machine configuration containing VRF interface definitions.
            Example:
            {
                'cloud_init': {
                    'netplan': {
                        'network': {
                            'vrfs': {
                                'mgmt-vrf': {
                                    'interfaces': ['vlan10']
                                }
                            }
                        }
                    }
                }
            }
        userdata (dict): Cloud-init user-data dictionary to be modified.

    Note:
        The function modifies the userdata dictionary in place by:
        - Adding systemd override files for network services
        - Adding systemd commands to enable VRF-aware SSH
        - Configuring DNS resolution for VRF context
    """
    # Get first VRF interface for systemd-networkd-wait-online
    vrf_interfaces = next(
        iter(vm["cloud_init"]["netplan"]["network"]["vrfs"].values())
    )["interfaces"]
    if len(vrf_interfaces) == 0:
        console_print("Error: No VRF interfaces defined!", ConsoleAttr.ERROR)
        console_print(
            "Declare at least one interface belonging to the VRF", ConsoleAttr.ERROR
        )
        sys.exit(1)
    vrf_interface = vrf_interfaces[0]

    # Replace VRF_INTERFACE in networkd-wait-online override content
    networkd_wait_online_override = networkd_wait_online_override_content.replace(
        "VRF_INTERFACE", vrf_interface
    )

    # Add VRF instructions to the runcmd section
    if "runcmd" not in userdata:
        userdata["runcmd"] = []
    userdata["runcmd"].extend(
        [
            # Create networkd-wait-online override file
            "mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d",
            f"cat <<'EOF' >{networkd_wait_online_override_file}\n{networkd_wait_online_override}\nEOF",
            # Create vrf-ssh service file
            f"cat <<'EOF' >{vrf_ssh_service_file}\n{vrf_ssh_service_content}\nEOF",
            # Reload systemd services
            "systemctl daemon-reload",
            # Restart systemd-networkd-wait-online service with VRF
            # interface tuning
            "systemctl restart systemd-networkd-wait-online.service",
            # Enable and start the new SSH service
            "systemctl enable vrf-ssh.service",
            "systemctl start vrf-ssh.service",
            # Replace resolv.conf and remove systemd-resolved
            # The systemd-resolved service listens on lo:127.0.0.53 which is
            # not reachable from the mgmt-vrf routing table
            "mv /etc/resolv.conf /etc/resolv.conf.bak",
            "echo 'nameserver 172.16.0.2' > /etc/resolv.conf",
            # Stop systemd-resolved service
            "systemctl stop systemd-resolved",
            "systemctl disable systemd-resolved",
        ]
    )


def create_cloud_init_seed_img(vm) -> str:
    """Create a cloud-init seed image for virtual machine configuration.

    This function generates a cloud-init seed image containing configuration data:
    - metadata: instance ID and hostname
    - user-data: users, packages, custom commands, VRF configuration
    - network-config: netplan network configuration

    Args:
        vm (dict): Virtual machine configuration containing cloud-init settings.
            Example:
            {
                'vm_name': 'vm1',
                'cloud_init': {
                    'hostname': 'vm1',
                    'users': [...],
                    'packages': [...],
                    'netplan': {
                        'network': {...}
                    }
                }
            }

    Returns:
        str: Path to created seed image file, or None if no cloud-init config.
            Format: <vm_name>-seed.img

    Raises:
        SystemExit: If cloud-localds command is missing or image creation fails.

    Example:
        >>> vm = {'vm_name': 'vm1', 'cloud_init': {...}}
        >>> seed_img = create_cloud_init_seed_img(vm)
        'vm1-seed.img'
    """
    if "cloud_init" not in vm:
        return None

    seed_img = f"{vm['vm_name']}-seed.img"

    # Check if seed.img should be created
    if not vm["cloud_init"].get("force_seed", False) and os.path.exists(seed_img):
        console_print(f"Using existing {seed_img}", ConsoleAttr.SUCCESS)
        return seed_img

    # Create a new seed.img
    console_print(f"Creating {seed_img}...", ConsoleAttr.INFO)
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create metadata file
        metadata = {
            "instance-id": vm["cloud_init"]["hostname"],
            "local-hostname": vm["cloud_init"]["hostname"],
        }
        with open(os.path.join(tmp_dir, "meta-data"), "w") as f:
            yaml.dump(metadata, f)

        # Create user-data file
        userdata = {}

        for key in [
            "users",
            "hostname",
            "packages",
            "runcmd",
            "write_files",
        ]:
            if key in vm["cloud_init"]:
                userdata[key] = vm["cloud_init"][key]
            else:
                if key in vm["cloud_init"]:
                    # Initialize empty lists for missing keys
                    userdata[key] = []

        # Check if VRF interfaces are defined
        if (
            "netplan" in vm["cloud_init"]
            and "vrfs" in vm["cloud_init"]["netplan"]["network"]
        ):
            create_vrf_userdata(vm, userdata)

        with open(f"{tmp_dir}/user-data", "w") as f:
            f.write("#cloud-config\n")
            yaml.dump(userdata, f)

        # Add netplan configuration
        if "netplan" in vm["cloud_init"]:
            networkconfig = {}
            networkconfig.update(vm["cloud_init"]["netplan"])

            with open(f"{tmp_dir}/network-config", "w") as f:
                f.write("# network-config\n")
                yaml.dump(networkconfig, f)

        # Create seed image
        seed_cmd = [
            "cloud-localds",
            seed_img,
            f"{tmp_dir}/user-data",
            f"{tmp_dir}/meta-data",
        ]
        if "netplan" in vm["cloud_init"]:
            seed_cmd.extend(["--network-config", f"{tmp_dir}/network-config"])
        run_subprocess(seed_cmd, "Error creating seed image file")
        console_print("done.", ConsoleAttr.SUCCESS)
        return seed_img


# Build the qemu command
def build_qemu_cmd(vm) -> list:
    """Build QEMU command line arguments for virtual machine startup.

    This function generates the appropriate command line arguments based on the VM type
    and configuration. It supports three types of VMs:
    - Linux: Uses ovs-startup.sh with cloud-init and optional storage devices
    - Windows: Uses ovs-startup.sh with optional storage devices
    - IOS XE: Uses ovs-iosxe.sh with multiple network interfaces

    Args:
        vm (dict): Virtual machine configuration containing OS type and settings.
            Example:
            {
                'vm_name': 'vm1',
                'os': 'linux',
                'memory': 2048,
                'tapnum': 1,
                'devices': {
                    'storage': [{
                        'dev_name': 'disk1.qcow2',
                        'size': '20G',
                        'bus': 'virtio'
                    }]
                },
                'cloud_init': {...}
            }

    Returns:
        list: Command line arguments for the appropriate startup script.
            Example for Linux:
            ['/path/to/ovs-startup.sh', 'vm1.qcow2', '2048', '1', 'linux', ...]

    Example:
        >>> vm = {'vm_name': 'vm1', 'os': 'linux', ...}
        >>> cmd = build_qemu_cmd(vm)
        >>> run_subprocess(cmd)
    """
    if vm["os"] == "linux":
        script = f"{MASTER_DIR}/scripts/ovs-startup.sh"
        vm_file = vm["vm_name"] + "." + get_image_format(vm["master_image"])
        cmd = [script, vm_file, str(vm["memory"]), str(vm["tapnum"]), "linux"]
        if "devices" in vm:
            dev_idx = 1
            dev_cmd = []
            if vm["devices"]["storage"]:
                for store in vm.get("devices", {}).get("storage", []):
                    create_device_image_file(store)
                    dev_filename = store["dev_name"]
                    dev_format = get_image_format(dev_filename)
                    dev_id = f"drive{dev_idx}"
                    dev_addr = store.get("addr", 0)
                    dev_cmd.extend(
                        build_device_cmd(
                            store, dev_filename, dev_format, dev_id, dev_idx, dev_addr
                        )
                    )
                    dev_idx += 1
                cmd.extend(dev_cmd)
        seed_img = create_cloud_init_seed_img(vm)
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
                    create_device_image_file(store)
                    dev_filename = store["dev_name"]
                    dev_format = get_image_format(dev_filename)
                    dev_id = f"drive{dev_idx}"
                    dev_addr = store.get("addr", 0)
                    dev_cmd.extend(
                        build_device_cmd(
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


def main():
    """Start virtual machines defined in a YAML configuration file.

    This function performs the following steps for each VM:
    1. Initialize terminal colors
    2. Parse command line arguments to get YAML config file
    3. Validate tap interface numbers are unique
    4. For each VM in the configuration:
        - Check if VM is not already running
        - Validate VM configuration against schema
        - Verify tap interfaces are available
        - Copy and prepare disk images
        - Setup UEFI boot if needed
        - Build and execute QEMU command

    Raises:
        SystemExit: If any validation or startup step fails:
            - Missing/invalid YAML file
            - Duplicate tap numbers
            - VM already running
            - Invalid VM configuration
            - Tap interface in use
            - Image copy failure
            - UEFI setup failure
            - VM startup failure

    Example:
        >>> lab-startup.py lab.yaml
        Starting vm1... done.
        Starting rtr1... done.
    """
    # Terminal color initialization
    colorama_init(autoreset=True)
    # Check if the yaml lab file is provided and read it
    arg = check_args()
    data = read_yaml(arg.file)
    # Check if tapnums are unique in the YAML file
    check_unique_tapnums(data)
    # Loop through the virtual machines
    for vm in data["kvm"]["vms"]:
        if not is_vm_running(vm["vm_name"]):
            # Validate the virtual machine YAML declaration
            check_yaml_declaration(vm)
            # Check if tap interfaces are not already in use
            if vm["os"] in ["linux", "windows"]:
                if is_tap_in_use(vm["tapnum"]):
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
            console_print(f"Starting {vm['vm_name']}...", ConsoleAttr.INFO)
            proc = run_subprocess(qemu_cmd, f"{vm['vm_name']} failed to start!")
            if proc.returncode == 0:
                console_print(f"{vm['vm_name']} started!", ConsoleAttr.SUCCESS)


if __name__ == "__main__":
    main()
