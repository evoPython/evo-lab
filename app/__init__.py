import os

from flask import Flask
from config import Config
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1
    )

    # Make sure the upload directory exists on startup rather than
    # failing the first time someone uploads a file.
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    # Import blueprints
    from app.portfolio.routes import portfolio
    from app.dashboard.routes import dashboard
    from app.controls.routes import controls
    from app.tools.routes import tools

    # Register blueprints
    app.register_blueprint(portfolio)
    app.register_blueprint(dashboard)
    app.register_blueprint(controls)
    app.register_blueprint(tools)

    # Lets templates conditionally show private nav links (Controls,
    # Tools, ...) without every route having to pass "is_personal"
    # in explicitly.
    @app.context_processor
    def inject_personal_status():
        from app.core.security import is_personal_device
        return dict(is_personal=is_personal_device())

    return app
