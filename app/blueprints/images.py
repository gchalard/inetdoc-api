from flask import Blueprint, request, jsonify, current_app, g

images_bp = Blueprint('images_bp', __name__)

@images_bp.before_app_request
def before_request():
    g.resources_controller = current_app.controller
    
@images_bp.route('/', methods=['GET'])
def get_images():
    return g.resources_controller.get_images()

@images_bp.route('/', methods=['POST'])
def create_image():
    return g.resources_controller.create_image()