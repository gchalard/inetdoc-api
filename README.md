# startup-scripts

This repository contains all the scripts used to start virtual machines of all
types on our type 2 hypervisors.

## Bash Scripts

These scripts are the low level scripts. They can be used as a reference to
start a single virtual machine.

- `ovs-startup.sh` starts all linux virtual machines

- `ovs-iosxe.sh` starts Cisco virtual routers such as Cloud Services Router
1000V or Cisco Catalyst 8000V Edge Software

- `ovs-nxos.sh` starts Cisco Nexus 9000v Switches such as 9300 or 9500

## Python Scripts

These scripts are declarative and can be used to start multiple virtual
machines.

To respect the teaching progression, the networking declaration is separated
from the virtual machine declaration. At the beginning, students will only use
virtual machines with automatic networking. Then, they will be able to declare
the network topology.

- `lab-startup.py` starts virtual machines declared in a YAML file of the form:

    ```yaml
    kvm:
      vms:
        - vm_name: # a virtual machine file name
          master_image: # debian-VERSION-amd64.qcow2 master image file to be used
          force_copy: # [true,false] force copy the master image to the VM image
          memory: # memory in MB
          tapnum: # tap interface number
    ```

    Invoked as `python3 lab-startup.py lab.yaml`

    See `lab-template.yaml` for an example.

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

    See `switch-template.yaml` for an example.

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