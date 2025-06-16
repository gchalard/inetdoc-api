from flask import Blueprint, current_app, g

cloud_init_bp = Blueprint('cloud_init_bp', __name__)

@cloud_init_bp.before_app_request
def before_request():
    g.resources_controller = current_app.controller
    
@cloud_init_bp.route('/', methods=['GET'])
def get_cloud_init():
    return g.resources_controller.get_cloud_init_disks()

@cloud_init_bp.route('/', methods=['POST'])
def create_cloud_init():
    print("Request received")
    return g.resources_controller.create_cloud_init()