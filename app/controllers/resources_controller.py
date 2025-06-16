# controllers/resources_controller.py

### BUILTIN IMPORTS ###
from flask import request, jsonify

### CUSTOM LIBRARY ###
from utils.utilities import *
from utils.exceptions import TapInUse, ImageInUse, DiskInUse, VMInUse
from utils.ovs_utils import OVSDBManager
from app.models.resources import Tap, Image, Disk, VM, CloudInit, User
from app.models.extensions import db

class ResourceController:
    
    def get_resources(self):
        
        taps = Tap.query.with_entities(Tap.id, Tap.name, Tap.status).all()
        images = Image.query.with_entities(Image.id, Image.name, Image.status).all()
        disks = Disk.query.with_entities(Disk.id, Disk.name, Disk.status, Disk.size).all()
        vms = VM.query.with_entities(VM.id, VM.name, VM.status).all()
        
        resources = list()
        
        for tap in taps:
            resources.append({
                "id": tap.id,
                "type": "TAP",
                "name": tap.name,
                "status": tap.status
            })
            
        for image in images:
            resources.append({
                "id": image.id,
                "type": "IMAGE",
                "name": image.name,
                "status": image.status
            })
            
        for disk in disks:
            resources.append({
                "id": disk.id,
                "type": "DISK",
                "name": disk.name,
                "status": disk.status,
                "size": disk.size
            })
            
        for vm in vms:
            resources.append({
                "id": vm.id,
                "type": "VM",
                "name": vm.name,
                "status": vm.status
            })
        
        return jsonify(
            resources
        )
        
    def delete_resources(self):
        return jsonify({
            "status": "success"
        }, 200)
        
    def create_tap(self, ovs_manager: OVSDBManager):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        try:
            tap = Tap(**data)
            tap.create(manager=ovs_manager)
            db.session.add(tap)
            db.session.commit()
            
        except TapInUse:
            return jsonify(
                {
                    "status": "Tap already in use"
                }, 409
            )
        except SystemExit:
            return jsonify(
                {
                    "status": "Failed to create tap"
                }, 500
            )
            
        return jsonify(
            {
                "status": "success",
                **data
            }, 200
        )
        
    def get_taps(self, ovs_manager: OVSDBManager):
        taps = Tap.query.with_entities(Tap.id, Tap.name, Tap.status).all()
        
        return jsonify(
            [
                {
                    "id": tap.id,
                    "name": tap.name,
                    "status": tap.status,
                } for tap in taps
            ]
        )
        
        
    def get_images(self):
        images = Image.query.with_entities(Image.id, Image.name, Image.status).all()
        
        return jsonify(
            [
                {
                    "id": image.id,
                    "name": image.name,
                    "status": image.status,
                } for image in images
            ]
        )
        
    def create_image(self):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        try:
            image = Image(
                name=data["name"],
                format=data["format"],
                url=data["url"],
                packages=data.get("packages", list())
            )
            image.create()
            db.session.add(image)
            db.session.commit()
            
            if "users" in data:
                for userdata in data["users"]:
                    user = User(**userdata)
                    image.customize(user)
            
        except ImageInUse:
            return jsonify(
                {
                    "status": "Image already in use"
                }
            ), 409
        except SystemExit:
            return jsonify(
                {
                    "status": "Failed to create image"
                }, 500
            )
            
        except Exception as e:
            print(f"Failed creating the image: {e}")
            return jsonify(
                {
                    "status": "Failed to create image"
                }, 500
            )
            
        return jsonify(
            {
                "status": "success",
                **data
            }, 200
        )
        
    def get_disks(self):
        disks = Disk.query.with_entities(Disk.id, Disk.name, Disk.status, Disk.size).all()
        
        return jsonify(
            [
                {
                    "id": disk.id,
                    "name": disk.name,
                    "status": disk.status,
                    "size": f"{disk.size} GB"
                } for disk in disks
            ]
        )
        
    def create_disk(self):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        try:
            disk = Disk(**data)
            disk.create()
            db.session.add(disk)
            db.session.commit()
            
        except DiskInUse:
            return jsonify(
                {
                    "status": "Disk already in use"
                }, 409
            )
        except SystemExit:
            return jsonify(
                {
                    "status": "Failed to create disk"
                }, 500
            )
            
        return jsonify(
            {
                "status": "success",
                "id": disk.id,
                "name": disk.name
            }, 201
        )
        
    def get_vms(self):
        vms = VM.query.with_entities(VM.id, VM.name, VM.status).all()
        
        return jsonify(
            [
                {
                    "id": vm.id,
                    "name": vm.name,
                    "status": vm.status,
                } for vm in vms
            ]
        )
        
    def create_vm(self):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        try:
            vm = VM(**data)
            db.session.add(vm)
            db.session.commit()
            
            vm.create()
            
        except VMInUse:
            return jsonify(
                {
                    "status": "VM already in use"
                }
            ), 409
        except SystemExit:
            return jsonify(
                {
                    "status": "Failed to create VM"
                }
            ), 500
            
        return jsonify(
            {
                "status": "success",
                **data
            }
        ), 200
        
    def create_cloud_init(self):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        time = datetime.datetime.now().time().strftime("%d%m%Y%H%M%S")
        
        try:
            cloud_init = CloudInit(
                name=f"{time}-{data['name']}",
                status="creating"
            )
            
            print("Initialized the cloud init disk...")
            print("Creating the cloud init disk...")
            cloud_init.create(
                network_config=data.get("network-config", dict()),
                userdata=data.get("userdata", dict()),
                metadata=data.get("metadata", dict())
            )
            print("Created the cloud init disk...")
            print("Adding the cloud init disk to the database...")
            db.session.add(cloud_init)
            print("Added the cloud init disk to the database...")
            print("Committing the changes...")
            db.session.commit()
            print("Committed the changes...")
            
        except Exception as e:
            print(f"Failed creating the CloudInit Disk: {e}")
            return jsonify(
                {
                    "status": "Failed to create cloud init"
                }
            ), 500
            
        return jsonify(
            {
                "status": "success",
            }
        ), 201
        
    def get_cloud_init_disks(self):
        cloud_init_disks = CloudInit.query.with_entities(CloudInit.id, CloudInit.name, CloudInit.status).all()
        
        return jsonify(
            [
                {
                    "id": cloud_init_disk.id,
                    "name": cloud_init_disk.name.split("-", 1)[1],
                    "status": cloud_init_disk.status,
                } for cloud_init_disk in cloud_init_disks
            ]
        )