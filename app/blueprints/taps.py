from flask import Blueprint, request, jsonify

from ..controllers.resources_controller import ResourceController

taps_bp = Blueprint('taps_bp', __name__)
resources_controller = ResourceController()

# @taps_bp.route('/', methods=['GET'])
# def get_resources():
#     return resources_controller.get_resources()

# @taps_bp.route('/', methods=['DELETE'])
# def delete_resources():
#     return resources_controller.delete_resources()

@taps_bp.route('/', methods=['POST'])
def create_tap():
    return resources_controller.create_tap()