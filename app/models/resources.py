from dataclasses import dataclass
import os
from typing import Optional
import requests

from utils.schemas import validate_tap, validate_schema, validate_image
from utils.utilities import is_tap_in_use
from utils.exceptions import TapInUse
from utils.ovs_utils import OVSDBManager

@dataclass
class Resource:
    id : int
    type : str
    name : str
    status : str
    
class Image(Resource):
    id : int
    type = "IMAGE"
    name : str
    format: str
    status : str
    url: str
    packages: Optional[list[str]]
    
    def __init__(self, id: int, name: str, format: str, status: str, url: str, packages: Optional[list[str]] = None):
        super().__init__(
            id = id,
            type = "IMAGE",
            name = name,
            status = status
        )
        
        self.url = url
        self.packages = packages
        
        # validate schema
        
        validate_image(
            data={
                "name": self.name,
                "url": self.url,
                "packages": self.packages
            }
        )
        
        # check image availability
        
        image_exists = os.path.exists(f"{self.name}.{self.format}")
        
        # image_in_use = is_image_in_use(name=self.name)
        
        # download image if not already exists
    

class Tap(Resource):
    id : int
    type = "TAP"
    tapnum : int
    name : str
    status : str
    mode : str
    tag : Optional[int] = None
    trunks : Optional[list[int]] = None
    
    def __init__(self, id: int, manager: OVSDBManager, tapnum: int, status: str, mode: str, tag: Optional[int] = None, trunks: Optional[list[int]] = list()):
        super().__init__(
            id = id,
            type = "TAP",
            name = f"tap{tapnum}",
            status = status            
        )
        
        self.mode = mode
        self.tag = tag
        self.trunks = trunks
        self.tapnum = tapnum
        self.manager = manager
        
        # validate schema
        print("Validating schema")
        validate_tap(
            data={
                "tap_name": self.name,
                "mode": self.mode,
                "tapnum": self.tapnum,
                "tag": self.tag,
                "trunks": self.trunks
            }
        )
        print("Schema validated")
        
        # check tap availability
        
        if is_tap_in_use(tapnum=self.tapnum):
            raise TapInUse(f"{self.name} is already in use")
        
        print("Tap not in use")
        
        # configure the tap
        self.manager.set_tap(
            tap_name=self.name,
            vlan_mode=self.mode,
            tag=self.tag if self.mode == "access" else [],
            trunks=self.trunks if self.mode == "trunk" else []
        )
        
        
        

class Disk(Resource):
    id : int
    type = "DISK"
    name : str
    status : str
    size : int

class VM(Resource):
    id : int
    type = "VM"
    name : str
    status : str
    ram : int
    vcpus : int
    os_family : str
    image : str
    disk : Disk
    taps : list[Tap]      