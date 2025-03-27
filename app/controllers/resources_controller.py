# controllers/resources_controller.py

### BUILTIN IMPORTS ###
from flask import request, jsonify

### CUSTOM LIBRARY ###
from utils.utilities import *
from utils.exceptions import TapInUse
from app.models.resources import Tap

class ResourceController:
    
    def get_resources(self):
        return jsonify(
            [
                {
                    "id": 1,
                    "type": "VM",
                    "name": "VM1",
                    "status": "running"
                },
                {
                    "id": 2,
                    "type": "TAP",
                    "name": "TAP1",
                    "status": "listening"
                },
                {
                    "id": 3,
                    "type": "DISK",
                    "name": "DISK1",
                    "status": "mounted"
                }
            ]
        )
        
    def delete_resources(self):
        return jsonify({
            "status": "success"
        }, 200)
        
    def create_tap(self):
        data = request.get_json()
        
        print(f"Request received : {data}")
        
        try:
            tap = Tap(**data)
            
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
                "status": "success"
            }, 200
        )
        
        
    def create_vm(self):
        data = request.get_json()
        
        # STEP 1 : VALIDATE THE JSON
        
        # STEP 2 : CREATE THE VM CLASS OBJECT
        
        # STEP 3 : CREATE THE VM