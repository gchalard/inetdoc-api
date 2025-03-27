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

from utils.constants import MASTER_DIR, TEMPLATE_DIR, OVMF_CODE, OVMF_VARS, CLOUD_INIT_NETPLAN_FILE
from utils.console_attr import ConsoleAttr

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
