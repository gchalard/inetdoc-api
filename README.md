# Virtual machines startup scripts

This repository contains all the scripts used to start virtual machines of all
types on our type-2 hypervisors.

In this context, a type 2 hypervisor is a KVM hypervisor running on a bare metal
server with Debian GNU/Linux. The hypervisor is configured with Open vSwitch
(OVS) to connect and manage both the virtual and physical networks.

A large number of tap interfaces are provided on the hypervisor **dsw-host** switch
for the students to run their virtual machines. These tap interfaces are
configured in access mode by default and belong to a VLAN with automatic IPv6
and IPv4 addressing. As the students progress, they will be able to configure
the swicth port to trunk mode and manage VLANs themselves.

## Bash Scripts

These scripts are the low level scripts. They can be used as a reference to
start a single virtual machine.

- `ovs-startup.sh` starts all linux virtual machines. It includes:

  - Configuration of TAP interfaces
  - Generation of SPICE passwords
  - Support for UEFI boot with OVMF
  - Advanced QEMU options for performance and security
  - Management of different GPU drivers
    - qxl with 64MB of video memory for Linux virtual machines
    - qxl-vga with 256MB of video memory for Windows virtual machines
  - Management of TPM support with swtpm

- `ovs-iosxe.sh` starts Cisco virtual routers such as Cloud Services Router
  1000V or Cisco Catalyst 8000V Edge Software. It includes:

  - Configuration of 3 TAP interfaces like the physical ISR4321 routers

- `ovs-nxos.sh` starts Cisco Nexus 9000v Switches such as 9300 or 9500

## Python Scripts

These scripts are declarative and can be used to start multiple virtual
machines.

To respect the teaching progression, the networking declaration is separated
from the virtual machine declaration. At the beginning, students will only use
virtual machines with automatic networking. Then, they will be able to declare
the network topology.

- `lab-startup.py` manages the startup of multiple virtual machines defined in a YAML file. It includes:

  - Verification of the uniqueness of TAP interface numbers
  - Creation of storage images if they do not exist for Linux or Windows OS
  - Building and executing QEMU commands based on the configuration
  - Handling different operating systems (`linux`, `windows`, `iosxe`)

  Example of a Linux YAML file:

  ```yaml
  kvm:
    vms:
      - vm_name: # a virtual machine file name
        os: # [linux, windows] operating system
        master_image: # debian-VERSION-amd64.qcow2 master image file to be used
        force_copy: # [true,false] force copy the master image to the VM image
        memory: # memory in MB
        tapnum: # tap interface number
        devices:
          storage:
            - dev_name: # supplemental disk file name with its extension to set format
              type: disk
              size: 32G # size of the disk
              bus: # [scsi, virtio, nvme] bus type
  ```

  Example of an IOSXE YAML file:

  ```yaml
  kvm:
    vms:
      - vm_name: # a virtual router file name
        os: iosxe
        master_image: # c8000v-VERSION.qcow2 master image file to be used
        force_copy: # [true,false] force copy the master image to the VM image
        tapnumlist: [10, 11, 12]
  ```

  Invoked as `python3 lab-startup.py lab.yaml`

  See [linux-lab.yaml](templates/linux-lab.yaml) or
  [iosxe-lab.yaml](templates/iosxe-lab.yaml) for examples.

- `switch-conf.py` sets the configuration of the hypervisor switch ports
  declared in a YAML file of the form:

  ```yaml
  ovs:
    switches:
      - name: SWITCH_NAME
        ports:
          - name: tapXXX
            type: OVSPort
            vlan_mode: access
            tag: VLAN_ID_X
          - name: tapYYY
            type: OVSPort
            vlan_mode: access
            tag: VLAN_ID_Y
          - name: tapZZZ
            type: OVSPort
            vlan_mode: trunk
            trunks: [VLAN_ID_X, VLAN_ID_Y]
  ```

  Invoked as `python3 switch-conf.py switch.yaml`

  See [switch.yaml](templates/switch.yaml) for an example.

## `ovs-startup.sh` script main characteristics

The `ovs-startup.sh` script has several differences compared to the most common
QEMU virtual machine scripts. Here are the main ones:

1. Integration with Open vSwitch (OVS):
   The script is designed to start virtual machines connected to Open vSwitch
   ports via existing TAP interfaces. This allows for advanced virtual network
   management.

2. Use of TPM (Trusted Platform Module):
   The script includes the configuration and startup of a TPM emulator (swtpm),
   which adds an extra layer of security by enabling TPM usage for virtual
   machines.

3. UEFI Support with OVMF:
   The script uses UEFI boot files provided by the OVMF package. This is
   particularly useful for modern operating systems that require UEFI.

4. SPICE Password Generation:
   The script automatically generates passwords for SPICE sessions and stores
   them securely. SPICE is used to provide graphical access to virtual
   machines, and automatic password management enhances security and
   convenience.

5. Advanced QEMU Options Configuration:
   The script uses advanced QEMU configuration with specific options for
   performance and security, such as -cpu max with multiple security options
   enabled, -device intel-iommu, and -object rng-random.

6. Network Interfaces and VLANs Management:
   The script checks and configures the VLAN modes of network interfaces,
   allowing fine-grained management of virtual networks and VLANs associated
   with virtual machines.

7. Use of ionice and nohup:
   The script uses ionice to set I/O priority and nohup to run QEMU in the
   background, ensuring that the process continues to run even after the user
   disconnects.

The design idea is to make the `ovs-startup.sh` script a flexible tool for
virtual machines management with tight integration with Open vSwitch and advanced
security features.

## Setting up the user environment

Here are the commands to set up the environment on the hypervisor on the first
connection:

```bash
ln -s /var/cache/kvm/masters ~
mkdir ~/vm
ln -s ~/masters/scripts ~/vm/
```

Once this basic setup is done for beginners, users can customize their own
directories.

## Setting up the hypervisor environment

The hypervisoir main directory is `/var/cache/kvm/masters`. It contains both the
virtual machine master images and the scripts to start the virtual machines.

Here is a sample list of the `masters` directory:

```bash
ls -1 /var/cache/kvm/masters/*.qcow2
/var/cache/kvm/masters/c8000v-universalk9.17.15.01a.qcow2
/var/cache/kvm/masters/debian-stable-amd64.qcow2
/var/cache/kvm/masters/debian-testing-amd64.qcow2
/var/cache/kvm/masters/nexus9300v64.10.4.2.F.qcow2
/var/cache/kvm/masters/nexus9500v64.10.4.2.F.qcow2
/var/cache/kvm/masters/ubuntu-24.04-desktop.qcow2
/var/cache/kvm/masters/ubuntu-24.04-devnet.qcow2
/var/cache/kvm/masters/ubuntu-24.04-server.qcow2
/var/cache/kvm/masters/win11-mac.qcow2
/var/cache/kvm/masters/win11.qcow2
/var/cache/kvm/masters/win22-server.qcow2
```

## Installation

Stated that `git` is installed on the hypervisor, the following command will
clone the repository in the `/var/cache/kvm/masters` directory:

```bash
sudo bash -c "mkdir -p /var/cache/kvm/masters && git clone https://gitlab.inetdoc.net/labs/startup-scripts /var/cache/kvm/masters"
```
