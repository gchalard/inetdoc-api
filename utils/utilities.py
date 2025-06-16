# utils/utilities.py

### BUITLIN IMPORTS ###
import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
from schema import And, Optional, Or, Schema, SchemaError
import time
from typing import Optional, List, Dict
import yaml

### LIBRARY IMPORT ###
from utils.console_attr import ConsoleAttr, console_print
from utils.constants import *


### CONSTANTS
ALLOWED_CONFIG_TYPE = [
    "cloud-config",
    "network-config"
]

CLOUD_INIT_FILES_DIR = "cloud_init_files"

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

def validate_cloud_init_config(config_file_path: str, schema_type: str) -> subprocess.CompletedProcess:
    """
        Function to validate cloud-init config file 
        Args:
            - config_file_path: str, String for the config file path to check
            - schema_type: str, String for the type of config file
        Raises:
            - FileNotFoundError if the provided config file path is wrong
            - KeyError if the provided type isn't allowed
            - SystemExit on validation error
    """
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"The provided config file path doesn't exist : {config_file_path}")
    
    if not schema_type in ALLOWED_CONFIG_TYPE:
        raise KeyError(f"The provided config type isn't allowed : {schema_type}")

    args = [
        "cloud-init",
        "schema",
        "--anotate",
        "--schema-type",
        schema_type,
        "--config-file",
        config_file_path
    ]
    run_subprocess(cmd=args, error_msg="Failed validating cloud-init config file")

def create_cloud_init_image(
        name: str,
        network_config: Optional[Dict[str,str]] = dict(),
        useradata: Optional[dict] = dict(),
        metadata: Optional[dict] = dict()
) -> subprocess.CompletedProcess :
    
    print("Creating the cloud init disk...")
    time = datetime.datetime.now().time().strftime("%d%m%Y%H%M%S")

    print("userdata: ", useradata)
    print("metadata: ", metadata)
    print("network_config: ", network_config)
    
    if not os.path.exists(CLOUD_INIT_FILES_DIR):
        os.makedirs(CLOUD_INIT_FILES_DIR)
    
    # Create the network_config yaml file
    network_config_file_name = f"{time}_network_config.yaml"
    network_config_file_path = Path(CLOUD_INIT_FILES_DIR) / network_config_file_name
    try :
        with open(network_config_file_path, "w") as network_config_file:
            yaml.dump(network_config, network_config_file)
    except Exception as e :
        print(f"Failed creating cloud-init network config file : {e}")
        raise yaml.error.YAMLError(e)
    # try:
    #     validate_cloud_init_config(network_config_file_path, "network-config")
    # except SystemExit as e: 
    #     print(f"Failed validating cloud-init network config file : {e}")
    #     sys.exit(1)

    # Create the userdata config yaml file
    useradata_config_file_name = f"{time}_userdata.yaml"
    useradata_config_file_path = Path(CLOUD_INIT_FILES_DIR) / useradata_config_file_name
    try :
        with open(useradata_config_file_path, "w") as useradata_config_file:
            useradata_config_file.write("#cloud-config\n")
            yaml.dump(useradata, useradata_config_file)
    except Exception as e :
        print(f"Failed creating cloud-init user data config file : {e}")
        raise yaml.error.YAMLError(e)
    # try:
    #     validate_cloud_init_config(useradata_config_file_path, "cloud-config")
    # except SystemExit:
    #     sys.exit(1)

    # Create the metadata config yaml file
    metadata_config_file_name = f"{time}_metadata.yaml"
    metadata_config_file_path = Path(CLOUD_INIT_FILES_DIR) / metadata_config_file_name
    try :
        with open(metadata_config_file_path, "w") as metadata_config_file:
            print("metadata: ", metadata)
            yaml.dump(metadata, metadata_config_file)
    except Exception as e :
        print(f"Failed creating cloud-init metadata config file : {e}")
        raise yaml.error.YAMLError(e)
    
    args = [
        "cloud-localds"
    ]
    
    if network_config != dict():
        args.append("--network-config")
        args.append(network_config_file_path)
    
    args.append(f"{name}.img")
    args.append(useradata_config_file_path)
        
    if metadata != dict():
        args.append(metadata_config_file_path)
    
    run_subprocess(
        cmd=args,
        error_msg="Failed creating cloud-init image"
    )
    
def configure_tap(name: str, mode: str, tag: Optional[int] = None, trunks: Optional[list[int]] = None):
    args = [
        "sudo",
        "ovs-vsctl",
        "set",
        "port",
        name,
        f"vlan_mode={mode}"
    ]
    
    if mode == "access":
        trunks = "[]"
        
    if mode == "trunks":
        tag = "[]"
        trunks = "[" + ",".join(trunks) + "]"
        
    args += [
        f"tag={tag}",
        f"trunks={trunks}"
    ]
    
    result = run_subprocess(cmd=args, error_msg=f"Failed configuring {name}")
    
    return result.returncode
        

def is_image_in_use(name: str) -> bool:
    """
    Check whether an image is in use by a VM.
    
    Args:
        name (str): The name of the image to check.
        
    Returns:
        bool: True if the image is in use, False otherwise.
    """
    cmd = f"pgrep -a qemu | grep {name}"
    try:
        output = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError:
        return False
    if output:
        return True
    
    return False

def is_disk_in_use(name: str) -> bool:
    """
    Check whether a disk is in use by a VM.

    Args:
        name (str): The name of the disk to check.

    Returns:
        bool: True if the disk is in use, False otherwise.
    """
    
    cmd = f"pgrep -a qemu | grep {name}"
    try:
        output = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError:
        return False
    if output:
        return True
    
    return False

def tpm_emulate(path: Path)->None:
    """Run the software TPM emulator

    Args:
        path (Path): The path to the software TPM directory
        
    Raises:
        SystemExit: If the command fails
        FileNotFoundError: If the TPM directory is not found
    """
    
    wait = 0
    
    cmd = [
        "swtpm",
        "socket",
        "--tpmstate",
        f"dir={path}",
        "--ctrl",
        f"type=unixio,path={path}/swtpm-sock",
        "--log",
        f"file={path}/swtpm.log",
        "--tpm2",
        "--terminate"
    ]
    
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    while not os.path.exists(f"{path}/swtpm-sock") and wait < 20:
        print("Waiting for swtpm to start...")
        time.sleep(1)
        wait += 1
    
def customize_image(
    image: Path,
    username: str,
    password: Optional[str] = None,
    shell: Optional[str] = "/bin/bash",
    groups: Optional[List[str]] = None,
    ssh_keys: Optional[List[str]] = None,
    packages: Optional[List[str]] = None  
) -> None:
    
    cmd = [
        "virt-customize",
        "--format",
        "qcow2",
        "--update",
        "--run-command",
        f"adduser --gecos \"\" --disabled-password {username}{' --shell ' + shell if shell else ''}"
    ]

    if password:
        cmd.append("--password")
        cmd.append(f"{username}:password:{password}")

    if groups:
        for group in groups:
            cmd.append("--run-command")
            cmd.append(f"adduser {username} {group}")

    if ssh_keys:
        for key in ssh_keys:
            cmd.append("--ssh-inject")
            cmd.append(f"{username}:string:{key}")
            
    if packages:
        cmd.append("--install")
        cmd.append(f"{','.join(packages)}")
            
    cmd.append("-a")
    cmd.append(f"{image}")

    run_subprocess(
        cmd=cmd,
        error_msg="Failed to customize image"
    )