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


# Use argparse to check if --help or -h is provided or if the yaml file is provided
def check_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="YAML switch configuration file to read")
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


# Get the switch names from declarative configuration
def get_switch_names(switch_config):
    for switch in switch_config["ovs"]["switches"]:
        sw_list = switch["name"].split(",")
    return sw_list


# Check if the switch name already exists on the system
def check_switch_exists(switch):
    result = subprocess.run(
        ["sudo", "ovs-vsctl", "br-exists", switch],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # nosec
    if result.returncode == 0:
        return True
    else:
        return False


# Get all of a switch's port parameters from declarative configuration
def get_port_parameters(switch, switch_config):
    return switch_config["ovs"]["switches"]["name" == switch]["ports"]


# check if the switch port in configuration already exist
def check_port_exists(switch, port_name):
    result = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "port-to-br", port_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    if re.match(switch, result):
        return True
    else:
        return False


# Get switch port vlan_mode
def get_port_vlan_mode(port_name):
    result = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", port_name, "vlan_mode"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    return result


# Get switch port tag
def get_port_tag(port_name):
    result = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", port_name, "tag"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    return result


# Get switch port trunks
def get_port_trunks(port_name):
    result = (
        subprocess.run(
            ["sudo", "ovs-vsctl", "get", "port", port_name, "trunks"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # nosec
        .stdout.decode("utf-8")
        .strip()
    )
    return result


# Configure the switch ports according to the ports attributes
def configure_switch_ports(switch, switch_config):
    for port in get_port_parameters(switch, switch_config):
        # Add the port to the switch if it does not exist
        if check_port_exists(switch, port["name"]):
            # Set the port vlan_mode if it is different from the configuration
            if get_port_vlan_mode(port["name"]) != port["vlan_mode"]:
                subprocess.run(
                    [
                        "sudo",
                        "ovs-vsctl",
                        "set",
                        "port",
                        port["name"],
                        f'vlan_mode={port["vlan_mode"]}',
                    ]
                )  # nosec
                print(
                    f"{Fore.BLUE}>> Port {port['name']} vlan_mode set to {port['vlan_mode']}{Style.RESET_ALL}"
                )  # noqa: E501
            else:
                print(
                    f"{Fore.GREEN}>> Port {port['name']} vlan_mode is already set to {port['vlan_mode']}{Style.RESET_ALL}"
                )
            # Set the port tag if the vlan_mode is access
            if port["vlan_mode"] == "access":
                # Set the port tag if it is different from the configuration
                if get_port_tag(port["name"]) != str(port["tag"]):
                    subprocess.run(
                        [
                            "sudo",
                            "ovs-vsctl",
                            "set",
                            "port",
                            port["name"],
                            f'tag={port["tag"]}',
                        ]
                    )  # nosec
                    print(
                        f"{Fore.BLUE}>> Port {port['name']} tag set to {port['tag']}{Style.RESET_ALL}"
                    )
                else:
                    print(
                        f"{Fore.GREEN}>> Port {port['name']} tag is already set to {port['tag']}{Style.RESET_ALL}"
                    )
            # Set the port trunks if the vlan_mode is trunk
            if port["vlan_mode"] == "trunk":
                # Set the port trunks if it is different from the configuration
                if get_port_trunks(port["name"]) != str(port["trunks"]):
                    subprocess.run(
                        [
                            "sudo",
                            "ovs-vsctl",
                            "set",
                            "port",
                            port["name"],
                            f'trunks={port["trunks"]}',
                        ]
                    )  # nosec
                    print(
                        f"{Fore.BLUE}>> Port {port['name']} trunks set to {port['trunks']}{Style.RESET_ALL}"
                    )
                else:
                    print(
                        f"{Fore.GREEN}>> Port {port['name']} trunks is already set to {port['trunks']}{Style.RESET_ALL}"
                    )
        else:
            print(
                f"{Fore.RED}>> Port {port['name']} does not exist on switch {switch}{Style.RESET_ALL}"
            )


# main function
def main():
    arg = check_args()
    conf = read_yaml(arg.file)
    # Terminal color initialization
    colorama_init(autoreset=True)
    # Get the list of switch names from the configuration
    switches_to_configure = get_switch_names(conf)
    existing_switches = []
    for sw in switches_to_configure:
        if check_switch_exists(sw):
            existing_switches.append(sw)
        else:
            print(f"{Fore.RED}>> Switch {sw} does not exist!{Style.RESET_ALL}")
            sys.exit(1)
    print("-" * 40)
    for sw in existing_switches:
        print(f"Configuring switch {Style.BRIGHT}{sw}{Style.RESET_ALL}")
        configure_switch_ports(sw, conf)
    print("-" * 40)


__main__ = main()
