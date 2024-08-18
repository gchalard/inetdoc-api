#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import subprocess  # nosec B404
import sys

import yaml


# a function that uses argparse to check if
# --help or -h is provided or if the yaml file is provided
def check_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="YAML switch configuration file to read")
    args = parser.parse_args()
    return args


# a function that reads the yaml file and returns the data
def read_yaml(file):
    # check if the yaml file exists
    if not os.path.exists(file):
        print(f"Error: {file} not found!")
        sys.exit(1)

    # open the yaml file
    with open(file) as f:
        data = yaml.safe_load(f)
    return data


# Get the switch names from the configuration
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


# main function
def main():
    arg = check_args()
    conf = read_yaml(arg.file)
    # Get the list of switch names from the configuration
    switch_list = get_switch_names(conf)
    existing_switches = []
    for sw in switch_list:
        if check_switch_exists(sw):
            existing_switches.append(sw)
    print("-" * 40)
    print(f"Already existing switches to be configured: {existing_switches}")


__main__ = main()
