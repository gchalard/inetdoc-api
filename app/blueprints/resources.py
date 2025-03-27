from flask import Blueprint, request, jsonify

from ..controllers.resources_controller import ResourceController

resources_bp = Blueprint('resources_bp', __name__)
resources_controller = ResourceController()

@resources_bp.route('/', methods=['GET'])
def get_resources():
    return resources_controller.get_resources()

@resources_bp.route('/', methods=['DELETE'])
def delete_resources():
    return resources_controller.delete_resources()
