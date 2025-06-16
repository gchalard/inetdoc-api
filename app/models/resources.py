from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Optional
import requests
from sqlalchemy import Column, Integer, String, ForeignKey, ARRAY
from sqlalchemy.orm import relationship
import shutil
from typing import Any, Dict, List
import yaml

from .extensions import db, s3

from utils.schemas import validate_tap, validate_schema, validate_image
from utils.utilities import is_tap_in_use, is_image_in_use, is_disk_in_use, run_subprocess, is_vm_running, tpm_emulate, create_cloud_init_image, validate_cloud_init_config, customize_image
from utils.exceptions import TapInUse, ImageInUse, DiskInUse, VMInUse
from utils.ovs_utils import OVSDBManager

IMAGE_BUCKET = "inetdoc-images"

class User:
    def __init__(self, username: str, password: Optional[str] = None, shell: Optional[str] = "/bin/bash", groups: Optional[List[str]] = None, ssh_keys: Optional[List[str]] = None):
        self.username = username
        self.password = password
        self.shell = shell
        self.groups = groups
        self.ssh_keys = ssh_keys
        

class Package(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("image.id"))
    name = Column(String, nullable=False)

class Image(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = "IMAGE"
    name = Column(String, nullable=False)
    format = Column(String, nullable=False)
    status = Column(String, nullable=False)
    url = Column(String, nullable=False)
    packages = relationship("Package", backref="image")
    
    def __init__(self, name: str, format: str, url: str, packages: Optional[List[str]] = list()):
        self.name = name
        self.format = format
        self.url = url
        self.status = "AVAILABLE"
        
        db.session.add(self)
        db.session.commit()
        
        for package in packages:
            pkg = Package(image_id=self.id, name=package)
            db.session.add(pkg)
            
        db.session.commit()
    
    def create(self):
                
        validate_image(
            data={
                "name": self.name,
                "url": self.url,
                "packages": [package.name for package in self.packages]
            }
        )
        
        # check image availability
        
        image_exists = os.path.exists(f"{self.name}.{self.format}")
        
        if image_exists:
            image_in_use = is_image_in_use(name=f"{self.name}.{self.format}")
            
            if image_in_use:
                raise ImageInUse(f"{self.name}.{self.format} is already in use")
        
        # download image if not already exists
        else:
            
            try:
                s3.download_file(IMAGE_BUCKET, f"{self.url}", f"{self.name}.{self.format}")
                print("Image downloaded successfully")
            except Exception as e:
                print(f"Failed downloading the image: {e}")
        
    def customize(self, user: User):
        print("Customizing image")
        
        customize_image(
            image=f"{self.name}.{self.format}",
            username=user.username,
            password=user.password,
            shell=user.shell,
            groups=user.groups,
            ssh_keys=user.ssh_keys,
            packages=[package.name for package in self.packages]
        )
        

class Trunk(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(Integer, nullable=False)
    tap_id = Column(Integer, ForeignKey("tap.id"))

class Tap(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = "TAP"
    tapnum = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    tag = Column(Integer, nullable=True)
    trunks = relationship("Trunk", backref="tap")
    
    def __init__(self, mode: str, tapnum: int, tag: Optional[int] = None, trunks: Optional[List[int]] = None):
        self.name = f"tap{tapnum}"
        self.mode = mode
        self.tapnum = tapnum
        self.status = "AVAILABLE"
        
        db.session.add(self)
        db.session.commit()
        
        if self.mode == "access":
            self.tag = tag
        
        if self.mode == "trunk":
            for trunk in trunks:
                trnk = Trunk(
                    tap_id=self.id,
                    number=trunk
                )
                db.session.add(trnk)
                
        db.session.commit()
    
    def create(self, manager: OVSDBManager):
        
        # validate schema
        print("Validating schema")
        validate_tap(
            data={
                "tap_name": self.name,
                "mode": self.mode,
                "tapnum": self.tapnum,
                "tag": self.tag,
                "trunks": [trunk.number for trunk in self.trunks]
            }
        )
        print("Schema validated")
        
        # check tap availability
        
        if is_tap_in_use(tapnum=self.tapnum):
            raise TapInUse(f"{self.name} is already in use")
        
        print("Tap not in use")
        
        # configure the tap
        manager.set_tap(
            tap_name=self.name,
            vlan_mode=self.mode,
            tag=self.tag if self.mode == "access" else [],
            trunks=[trunk.number for trunk in self.trunks] if self.mode == "trunk" else []
        )
        
        
        

class Disk(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = "DISK"
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    
    def create(
        self
    ):
        """
        Initialize a Disk object.

        Args:
        id (int): The ID of the Disk object.
        name (str): The name of the Disk object.
        status (str): The status of the Disk object.
        size (int): The size of the Disk in GB.

        Raises:
        DiskInUse: If the disk is already in use.
        """
        
        disk_exists = os.path.exists(f"{self.name}.qcow2")
        
        if disk_exists:
            disk_in_use = is_disk_in_use(name=f"{self.name}.qcow2")
            
            if disk_in_use:
                raise DiskInUse(f"{self.name}.qcow2 is already in use")
        
        
        cmd = [
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            f"{self.name}.qcow2",
            f"{self.size}G"
        ]
        run_subprocess(cmd, f"ERROR creating f{self.name}.qcow2 disk")
        

class CloudInit(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = "CLOUD INIT"
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    network_config_path = Column(String, nullable=False, default=f"{datetime.now().strftime("%d%m%Y%H%M%S")}_network_config.yaml")
    userdata_path = Column(String, nullable=False, default=f"{datetime.now().strftime("%d%m%Y%H%M%S")}_userdata.yaml")
    metadata_path = Column(String, nullable=False, default=f"{datetime.now().strftime("%d%m%Y%H%M%S")}_metadata.yaml")
    
    
    def create(self, network_config: Optional[Dict[str, Any]] = dict(), userdata: Optional[Dict[str, Any]] = dict(), metadata: Optional[Dict[str, Any]] = dict()):
        print("Creating ...")
        try:
            print("userdata: ", userdata)
            print("metadata: ", metadata)
            print("network_config: ", network_config)
            create_cloud_init_image(
                network_config=network_config,
                useradata=userdata,
                metadata=metadata,
                name=self.name
            )
        except Exception as e:
            print(f"Failed creating the CloudInit Disk: {e}")

class VM(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = "VM"
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    ram = Column(Integer, nullable=False)
    vcpus = Column(Integer, nullable=False)
    os_family = Column(String, nullable=False)
    image_id = Column(Integer, nullable=False)
    disk_id = Column(Integer, nullable=False)
    tap_id = Column(Integer, nullable=False)
    cloudinit_id = Column(Integer, nullable=True)
    
    def create(
        self
    ):
        """
        Initialize a VM object.

        Args:
        id (int): The ID of the VM object.
        name (str): The name of the VM object.
        status (str): The status of the VM object.
        ram (int): The amount of RAM in GB.
        vcpus (int): The number of virtual CPUs.
        os_family (str): The type of the operating system.
        image (Image): The image to boot from.
        disk (Disk): The disk to use.
        tap (Tap): The tap to connect.

        """
        vm_is_running = is_vm_running(vm=self.name)
        
        self.image = Image.query.filter_by(id=self.image_id).first()
        self.disk = Disk.query.filter_by(id=self.disk_id).first()
        self.tap = Tap.query.filter_by(id=self.tap_id).first()
        
        rightmost_byte = format(self.tap.tapnum % 256, "02x")
        second_rightmost_byte = format(self.tap.tapnum // 256, "02x")
        
        self.macaddress = f"b8:ad:ca:fe:{second_rightmost_byte}:{rightmost_byte}"
        
        if vm_is_running:
            raise VMInUse(f"{self.name} is already running")
        
        telnet_port = 2300 + self.tap.tapnum
        spice_port = 5900 + self.tap.tapnum
        
        if self.os_family == "linux":
            RAMQ=64
            gpu_driver=f"qxl,vgamem_mb={RAMQ},vram64_size_mb={RAMQ},vram_size_mb={RAMQ}"
        elif self.os_family == "windows":
            RAMQ=512
            gpu_driver=f"qxl-vga,vgamem_mb={RAMQ},vram64_size_mb={RAMQ},vram_size_mb={RAMQ}"
        else:
            raise Exception(f"OS family {self.os_family} is not supported")
        
        base_dir = Path(f"{self.id}-{self.name}")
        
        if not os.path.exists(base_dir):
            print("Base directory does not exist. Creating...")
            os.mkdir(base_dir)
        
        tpm_dir = base_dir / "TPM"
        
        if not os.path.exists(tpm_dir):
            print("TPM directory does not exist. Creating...")
            os.mkdir(tpm_dir)
            
        if not os.path.exists(tpm_dir / "swtpm-sock"):
            print("TPM socket does not exist. Creating...")
            tpm_emulate(path=tpm_dir)
        
        ovmf_src = Path("/usr/share/OVMF/OVMF_CODE_4M.secboot.fd")
        ovmf_dst = base_dir / "OVMF_CODE.fd"    
        if not os.path.exists(ovmf_dst):
            print("OVMF_VARS.fd does not exist. Creating...")
            os.symlink(src=ovmf_src, dst=ovmf_dst)
        
        if not os.path.exists(base_dir / "OVMF_VARS.fd"):
            print("OVMF_VARS.fd does not exist. Creating...")
            ovmf_vars_src = Path("/usr/share/OVMF/OVMF_VARS_4M.ms.fd")
            ovmf_vars_dst = base_dir / "OVMF_VARS.fd"
            shutil.copyfile(src=ovmf_vars_src, dst=ovmf_vars_dst)
        
        cmd = [
            "qemu-system-x86_64",
            "-machine", 
            "type=q35,smm=on,accel=kvm:tcg,kernel-irqchip=split",
            "-cpu", 
            "max,l3-cache=on,+vmx,pcid=on,spec-ctrl=on,stibp=on,ssbd=on,pdpe1gb=on,md-clear=on,vme=on,f16c=on,rdrand=on,tsc_adjust=on,xsaveopt=on,hypervisor=on,arat=off,abm=on",
            "-device", 
            "intel-iommu,intremap=on",
            "-smp", 
            "sockets=2,cores=4,threads=1",
            "-object", 
            f"memory-backend-ram,size={self.ram}G,id=mem0",
            "-m", 
            f"{self.ram}G,maxmem=32G",
            "-numa", 
            "node,nodeid=0,cpus=0-7,memdev=mem0",
            "-daemonize",
            "-name", 
            f"{self.name}",
            "-global",
            "ICH9-LPC.disable_s3=1",
            "-global", 
            "ICH9-LPC.disable_s4=1",
            "-device",
            f"virtio-net-pci,mq=on,vectors=18,netdev=net{self.tap.tapnum},disable-legacy=on,disable-modern=off,mac={self.macaddress}",
            "-netdev",
            f"type=tap,queues=8,ifname=tap{self.tap.tapnum},id=net{self.tap.tapnum},script=no,downscript=no,vhost=on",
            "-serial", 
            f"telnet:localhost:{telnet_port},server,nowait",
            "-device",
            "virtio-balloon-pci,deflate-on-oom=on,free-page-reporting=on",
            "-rtc",
            "base=localtime,clock=host",
            "-device",
            "i6300esb",
            "-watchdog-action",
            "poweroff",
            "-boot",
            "order=c,menu=on",
            "-drive",
            f"if=none,id=drive0,format={self.image.format},media=disk,file={self.image.name}.{self.image.format}",
            "-device",
            "nvme,drive=drive0,serial=feedcafe",
            "-global",
            "driver=cfi.pflash01,property=secure,value=on",
            "-drive",
            f"if=pflash,format=raw,unit=0,file={ovmf_dst},readonly=on",
            "-drive",
            f"if=pflash,format=raw,unit=1,file={base_dir}/OVMF_VARS.fd",
            "-k",
            "fr",
            "-vga",
            "none",
            "-device",
            gpu_driver,
            "-object",
            f"secret,id=spiceSec0,file={Path.home()}/.spice/spice.passwd",
            "-spice",
            f"port={spice_port},addr=localhost,password-secret=spiceSec0",
            "-device",
            "virtio-serial-pci",
            "-device",
            "virtserialport,chardev=spicechannel0,name=com.redhat.spice.0",
            "-chardev",
            "spicevmc,id=spicechannel0,name=vdagent",
            "-object",
            "rng-random,filename=/dev/urandom,id=rng0",
            "-device",
            "virtio-rng-pci,rng=rng0",
            "-chardev",
            f"socket,id=chrtpm,path={tpm_dir}/swtpm-sock",
            "-tpmdev",
            "emulator,id=tpm0,chardev=chrtpm",
            "-device",
            "tpm-tis,tpmdev=tpm0",
            "-usb",
            "-device",
            "usb-tablet,bus=usb-bus.0",
            "-device",
            "ich9-intel-hda,addr=1f.1",
            "-audiodev",
            "spice,id=snd0",
            "-device",
            "hda-output,audiodev=snd0"
        ]
        
        if self.cloudinit_id:
            cloudinit = CloudInit.query.with_entities(CloudInit.name).filter_by(id=self.cloudinit_id).first()
            cmd.append("-drive")
            cmd.append(f"if=virtio,format=raw,file={cloudinit.name}.img")
        
        run_subprocess(cmd, f"ERROR creating VM {self.name}")