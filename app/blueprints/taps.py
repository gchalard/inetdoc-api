from flask import Blueprint, request, jsonify, current_app, g

taps_bp = Blueprint('taps_bp', __name__)

@taps_bp.before_app_request
def before_request():
    g.resources_controller = current_app.controller
    g.ovs_manager = current_app.ovs_manager

# @taps_bp.route('/', methods=['GET'])
# def get_resources():
#     return resources_controller.get_resources()

# @taps_bp.route('/', methods=['DELETE'])
# def delete_resources():
#     return resources_controller.delete_resources()

@taps_bp.route('/', methods=['GET'])
def get_taps():
    return g.resources_controller.get_taps(g.ovs_manager)

@taps_bp.route('/', methods=['POST'])
def create_tap():
    return g.resources_controller.create_tap(g.ovs_manager)