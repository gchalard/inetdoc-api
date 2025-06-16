from flask import Flask

from app.blueprints.resources import resources_bp
from app.blueprints.taps import taps_bp
from app.blueprints.images import images_bp
from app.blueprints.disks import disks_bp
from app.blueprints.vms import vms_bp
from app.blueprints.cloud_init import cloud_init_bp

from app.controllers.resources_controller import ResourceController
from app.models.extensions import db
from utils.ovs_utils import OVSDBManager

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///resources.db"
    
    db.init_app(app=app)
    
    controller = ResourceController()
    ovs_manager = OVSDBManager()
    
    with app.app_context():
        db.create_all()
        app.controller = controller
        app.ovs_manager = ovs_manager
    
    app.register_blueprint(resources_bp, url_prefix="/resources")
    app.register_blueprint(taps_bp, url_prefix="/resources/taps")
    app.register_blueprint(images_bp, url_prefix="/resources/images")
    app.register_blueprint(disks_bp, url_prefix="/resources/disks")
    app.register_blueprint(vms_bp, url_prefix="/resources/vms")
    app.register_blueprint(cloud_init_bp, url_prefix="/resources/cloud-init")
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=30001)