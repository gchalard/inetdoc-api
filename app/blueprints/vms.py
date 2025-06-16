from flask import Blueprint, request, jsonify, current_app, g

vms_bp = Blueprint('vms_bp', __name__)

@vms_bp.before_app_request
def before_request():
    g.resources_controller = current_app.controller
    
@vms_bp.route('/', methods=['GET'])
def get_vms():
    return g.resources_controller.get_vms()

@vms_bp.route('/', methods=['POST'])
def create_vm():
    return g.resources_controller.create_vm()