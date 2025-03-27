from flask import Flask

from app.blueprints.resources import resources_bp
from app.blueprints.taps import taps_bp

def create_app():
    app = Flask(__name__)
    
    app.register_blueprint(resources_bp, url_prefix="/resources")
    app.register_blueprint(taps_bp, url_prefix="/resources/taps")
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=30001)