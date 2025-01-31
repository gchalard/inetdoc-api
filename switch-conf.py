#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is part of https://inetdoc.net project
#
# It configures Open vSwitch ports of existing switches on our type-2
# hypervisors. The switch ports can be configured as:
# - access ports with VLAN tagging
# - trunk ports with multiple VLANs
#
# Current features:
# - Validation of YAML configuration file
# - Configuration of existing switch ports
# - No modification if current configuration matches declarations
#
# Future features:
# - Creation of new switches
# - Creation of new switch ports
#
# File: switch-conf.py
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
import subprocess  # nosec B404
import sys

import yaml
from colorama import Fore, Style
from colorama import init as colorama_init
from schema import And, Optional, Or, Schema, SchemaError


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


# Validate YAML configuration against schema
def check_yaml_declaration(data):
    # Schema definitions
    port_schema = Schema(
        {
            "name": str,
            "type": "OVSPort",
            "vlan_mode": Or("access", "trunk"),
            Optional("tag"): And(int, lambda n: 1 <= n <= 4094),
            Optional("trunks"): [And(int, lambda n: 1 <= n <= 4094)],
        }
    )

    switch_schema = Schema(
        {"ovs": {"switches": [{"name": str, "ports": [port_schema]}]}}
    )

    try:
        switch_schema.validate(data)
    except SchemaError as e:
        print(f"{Fore.LIGHTRED_EX}Error in YAML declaration: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)

    return data


# Run an ovs command and return the output
def run_ovs_command(command):
    try:
        result = subprocess.run(
            ["sudo", "ovs-vsctl"] + command, capture_output=True, text=True
        )  # nosec B603
        if result.returncode != 0:
            raise Exception(f"Error executing command: {result.stderr}")
        return result.stdout.strip()
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Error: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


# Get the switch names from declarative configuration
def get_switch_names(switch_config):
    for switch in switch_config["ovs"]["switches"]:
        sw_list = switch["name"].split(",")
    return sw_list


# Check if the switch name already exists on the system
def check_switch_exists(switch):
    try:
        run_ovs_command(["br-exists", switch])
        return True
    except Exception:
        return False


# Get all of a switch's port parameters from declarative configuration
def get_port_parameters(switch, switch_config):
    return switch_config["ovs"]["switches"]["name" == switch]["ports"]


# check if the switch port in configuration already exist
# and belongs to the declared switch
def check_port_exists(switch, port_name):
    try:
        result = run_ovs_command(["port-to-br", port_name])
        return result == switch
    except Exception:
        return False


# Get switch port vlan_mode
def get_port_vlan_mode(port):
    try:
        return run_ovs_command(["get", "port", port, "vlan_mode"]).strip('"')
    except Exception:
        return None


# Get switch port tag
def get_port_tag(port):
    try:
        return run_ovs_command(["get", "port", port, "tag"])
    except Exception:
        return None


# Get switch port trunks
def get_port_trunks(port_name):
    try:
        result = run_ovs_command(["get", "port", port_name, "trunks"])
        if result == "[]":  # Empty trunk list
            return []
        # Strip brackets and split on commas
        return [int(vlan) for vlan in result.strip("[]").split(",") if vlan]
    except Exception:
        return None


# Configure the switch ports according to the ports attributes
def configure_switch_ports(switch, switch_config):
    for port in get_port_parameters(switch, switch_config):
        # Check if the port exists on the switch with the right name
        if check_port_exists(switch, port["name"]):
            # Check if the right vlan_mode is set
            current_mode = get_port_vlan_mode(port["name"])
            if current_mode != port["vlan_mode"]:
                run_ovs_command(
                    ["set", "port", port["name"], f'vlan_mode={port["vlan_mode"]}']
                )
                print(
                    f"{Fore.LIGHTBLUE_EX}>> Port {port['name']} vlan_mode set to {port['vlan_mode']}{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.LIGHTGREEN_EX}>> Port {port['name']} vlan_mode is already set to {port['vlan_mode']}{Style.RESET_ALL}"
                )

            # Define the VLAN the port belongs to in access mode
            if port["vlan_mode"] == "access":
                current_tag = get_port_tag(port["name"])
                if current_tag != str(port["tag"]):
                    run_ovs_command(["set", "port", port["name"], f'tag={port["tag"]}'])
                    print(
                        f"{Fore.LIGHTBLUE_EX}>> Port {port['name']} tag set to {port['tag']}{Style.RESET_ALL}"
                    )
                else:
                    print(
                        f"{Fore.LIGHTGREEN_EX}>> Port {port['name']} tag is already set to {port['tag']}{Style.RESET_ALL}"
                    )

            # Define the allowed VLAN list for the port in trunk mode
            elif port["vlan_mode"] == "trunk":
                current_trunks = get_port_trunks(port["name"])
                if current_trunks != port["trunks"]:
                    trunk_vlans = "[" + ",".join(map(str, port["trunks"])) + "]"
                    run_ovs_command(
                        ["set", "port", port["name"], f"trunks={trunk_vlans}"]
                    )
                    print(
                        f"{Fore.LIGHTBLUE_EX}>> Port {port['name']} trunks set to {trunk_vlans}{Style.RESET_ALL}"
                    )
                else:
                    print(
                        f"{Fore.LIGHTGREEN_EX}>> Port {port['name']} trunks are already set to {current_trunks}{Style.RESET_ALL}"
                    )
        else:
            print(
                f"{Fore.LIGHTRED_EX}>> Port {port['name']} does not exist on switch {switch}{Style.RESET_ALL}"
            )


# main function
def main():
    arg = check_args()
    conf = read_yaml(arg.file)
    # Terminal color initialization
    colorama_init(autoreset=True)
    check_yaml_declaration(conf)
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


if __name__ == "__main__":
    main()
