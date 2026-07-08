from flask import Flask
from config import Config


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)


    # Import blueprints
    from app.portfolio.routes import portfolio
    from app.dashboard.routes import dashboard


    # Register blueprints
    app.register_blueprint(portfolio)
    app.register_blueprint(dashboard)


    return app
