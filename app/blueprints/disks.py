from flask import Blueprint, request, jsonify, current_app, g

disks_bp = Blueprint('disks_bp', __name__)

@disks_bp.before_app_request
def before_request():
    g.resources_controller = current_app.controller
    
@disks_bp.route('/', methods=['GET'])
def get_disks():
    return g.resources_controller.get_disks()

@disks_bp.route('/', methods=['POST'])
def create_disk():
    return g.resources_controller.create_disk()