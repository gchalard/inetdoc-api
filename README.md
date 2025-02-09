# Virtual Machine Startup Scripts

This repository contains scripts for starting various types of virtual machines
on our type-2 hypervisors.

## Table of Contents

- [Overview](#overview)
- [Bash Scripts](#bash-scripts)
  - [ovs-startup.sh](#ovs-startupsh)
  - [ovs-iosxe.sh](#ovs-iosxesh)
  - [ovs-nxos.sh](#ovs-nxossh)
- [Python Scripts](#python-scripts)
  - [lab-startup.py](#lab-startuppy)
  - [switch-conf.py](#switch-confpy)
- [Installation](#installation)
  - [Hypervisor Environment Setup](#hypervisor-environment-setup)
  - [User Environment Setup](#user-environment-setup)
- [Cloud-init integration](#cloud-init-integration)
- [Additional storage devices](#additional-storage-devices)
- [Contribution](#contribution)
- [License](#license)

## Overview

In this setup, a type-2 hypervisor is a KVM hypervisor running on a bare metal
server with Debian GNU/Linux. The hypervisor is configured with Open vSwitch
(OVS) to manage both virtual and physical networks.

Numerous tap interfaces are provisioned on the hypervisor's **dsw-host** switch.
Students can use these tap interfaces to connect their virtual machines to the
lab infrastructure network.
The tap interfaces are initially configured by default in access mode and belong
to a single VLAN with automatic IPv6 and IPv4 addressing.

## Bash Scripts

These low-level scripts can be used as a reference to start a single virtual machine.

### ovs-startup.sh

This script starts all Linux virtual machines. It includes:

- TAP interface configuration
- SPICE password generation
- UEFI boot support with OVMF
- Advanced QEMU options for performance and security
- Management of different GPU drivers
- TPM support with swtpm

### Key Features of ovs-startup.sh

The `ovs-startup.sh` script has several differences from most common QEMU
scripts:

1. Integration with Open vSwitch (OVS)
2. Use of TPM (Trusted Platform Module)
3. UEFI Support with OVMF
4. SPICE Password Generation
5. Advanced QEMU Options Configuration
6. Network Interfaces and VLANs Management
7. Use of ionice and nohup

Usage example for a Debian virtual machine with 1GB of RAM and using `tap0`
switch port:

```bash
ovs-startup.sh debian-testing-amd64.qcow2 1024 0
```

### ovs-iosxe.sh

This script starts Cisco virtual routers such as Cloud Services Router 1000V or
Cisco Catalyst 8000V Edge Software. It configures 3 TAP interfaces like the
physical ISR4321 routers.

Usage example for a Cisco Catalyst 8000V Edge Software virtual router with 3 TAP
interfaces (`tap7`, `tap8`, `tap9`):

```bash
ovs-iosxe.sh c8000v-universalk9.17.16.01a.qcow2 7 8 9
```

### ovs-nxos.sh

This script starts Cisco Nexus 9000v Switches such as 9300 or 9500.

## Python Scripts

These declarative scripts can be used to configure Open vSwitch ports and launch
multiple virtual machines with additional storage devices and cloud-init
configuration options.

Installation of the `python3-colorama` and `python3-schema` packages on a Debian
system is required to run the Python scripts.

### lab-startup.py

This script manages the startup of multiple virtual machines defined in a YAML
file. It includes:

- Verification of TAP interface number uniqueness
- Creation of storage images if they don't exist for Linux or Windows OS
- Building and executing QEMU commands based on configuration
- Handling different operating systems (`linux`, `windows`, `iosxe`)

Usage example:

```bash
lab-startup.py lab.yaml
```

For YAML file examples, see [linux-lab.yaml](templates/linux-lab.yaml) or
[iosxe-lab.yaml](templates/iosxe-lab.yaml).

### switch-conf.py

The `switch-conf.py` script configures Open vSwitch ports using a declarative
YAML file. Current features include:

- VLAN mode configuration (access/trunk)
- VLAN tagging for access ports
- Multiple VLANs for trunk ports
- Configuration validation with schema
- Existing configuration check to avoid redundant changes

Usage example:

```bash
switch-conf.py switch.yaml
```

For a YAML file example, see [switch.yaml](templates/switch.yaml).

## Installation

Use the following instructions to set up the environment at the type-2
hypervisor system and user levels.

### Hypervisor Environment Setup

The hypervisor's main directory is `/var/cache/kvm/masters`. It contains both
the virtual machine master images and the scripts to start them.

Ensure `git` is installed on the hypervisor, then run the following command to
clone the repository into the `/var/cache/kvm/masters` directory:

```bash
# Create the main masters directory and clone the repository
sudo bash -c "mkdir -p /var/cache/kvm/masters && \
    git clone https://gitlab.inetdoc.net/labs/startup-scripts /var/cache/kvm/masters"

# Allow the kvm group users to run Open vSwitch commands without a password
echo "%kvm    ALL=(ALL) NOPASSWD: /usr/bin/ovs-vsctl, /usr/bin/ovs-ofctl, /usr/bin/ovs-appctl, !/usr/bin/ovs-vsctl del-br dsw-host" |\
    sudo tee /etc/sudoers.d/kvm

# Any authenticated user can run the ovs-vsctl command and launch virtual machines
echo "*;*;*;Al0000-2400;adm,kvm,netdev,wireshark" |\
    sudo tee -a /etc/security/group.conf
echo "auth	required			pam_group.so" |\
    sudo tee -a /etc/pam.d/common-auth
```

### User Environment Setup

To set up the environment on the hypervisor on first connection, run the
following commands:

```bash
ln -s /var/cache/kvm/masters ~
mkdir ~/vm
ln -s ~/masters/scripts ~/vm/
```

Check that groups are correctly set:

```bash
id
uid=10000(etudianttest) gid=10000 groupes=10000,4(adm),106(kvm),109(netdev),115(wireshark)
```

Add the `scripts` directory to the user's PATH:

```bash
cat << 'EOF' >> ~/.profile
if [[ ":$PATH:" != *":$HOME/masters/scripts:"* ]]; then
    PATH="$PATH:$HOME/masters/scripts"
fi
EOF
```

There we go! The scripts are now ready to be used.

## Cloud-init integration

When you want to set up a virtual machine configuration, **Cloud-init** is a
useful tool.
In our case, the configuration is set up using the YAML declaration file
starting with the `cloud-init:` keyword.

You can find an example in the `templates` directory (see
[cloud-init-lab.yaml](templates/cloud-init-lab.yaml)).
The `lab-startup.py` script will build a `seed.img` file containing the
cloud-init configuration declared in the YAML file.
The `seed.img` file will be attached to the virtual machine as a supplemental
disk.

### Cloud-init features

- Users creation with SSH public keys for authentication
- Hostname setting
- Packages installation
- Network configuration through Netplan.io

You can find two templates in the `templates` directory:

- [cloud-init-ovs-lab.yaml](templates/cloud-init-ovs-lab.yaml) which illustrates
  the installation of the `openvswitch-switch` package before to apply the netplan
  configuration
- [cloud-init-vrf-lab.yaml](templates/cloud-init-vrf-lab.yaml) which illustrates
  the configuration of a management VRF ('mgmt-vrf') dedicated to automation tools
  such as Ansible

## Additional storage devices

When you want to add additional storage devices to your virtual machine, you can
use the `devices:` keyword in the YAML file.
The `lab-startup.py` script will create the storage devices and attach them to
the virtual machine.

You can find an example in the `templates` directory (see
[linux-lab.yaml](templates/linux-lab.yaml)).

### Additional storage devices features

- The `name:` keyword is used to set the file name and its extension sets the
  format (.raw or .qcow2)
- The only `type:` supported is `disk` at the moment
- The `size:` keyword is used to set the size of the storage device in GB
- The `bus:` keyword is used to set the bus type (ide, scsi, virtio)

## Contribution

Contributions are welcome. To contribute :

- Clone or Fork the project
- Create a branch for the functionality
- Commit the changes
- Push to the branch
- Open a Pull Request

## License

This project is licensed under the GNU GPL v3 - see the [LICENSE](LICENSE.txt)
file for more details.
