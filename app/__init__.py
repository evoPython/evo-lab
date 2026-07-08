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


    # Import blueprints
    from app.portfolio.routes import portfolio
    from app.dashboard.routes import dashboard


    # Register blueprints
    app.register_blueprint(portfolio)
    app.register_blueprint(dashboard)


    return app
