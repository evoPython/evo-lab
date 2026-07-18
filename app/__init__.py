import os
from datetime import timedelta

from flask import Flask
from config import Config
from werkzeug.middleware.proxy_fix import ProxyFix

from app.modes.routes import modes


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(days=30)

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1
    )

    # Make sure the upload directory and db directory exist on startup.
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DB_PATH"]), exist_ok=True)

    from app.core.db import init_db
    init_db(app)

    # Import blueprints
    from app.portfolio.routes import portfolio
    from app.dashboard.routes import dashboard
    from app.controls.routes import controls
    from app.tools.routes import tools
    from app.niri.routes import niri
    from app.launcher.routes import launcher
    from app.media.routes import media
    from app.remote.routes import remote
    from app.auth.routes import auth
    from app.cross_remote.routes import cross_remote
    from app.letters.routes import letters

    # Register blueprints
    app.register_blueprint(portfolio)
    app.register_blueprint(dashboard)
    app.register_blueprint(controls)
    app.register_blueprint(tools)
    app.register_blueprint(niri)
    app.register_blueprint(launcher)
    app.register_blueprint(media)
    app.register_blueprint(remote)
    app.register_blueprint(auth)
    app.register_blueprint(cross_remote)
    app.register_blueprint(letters)
    app.register_blueprint(modes)

    # Lets templates conditionally show private nav links without
    # every route having to pass status flags in explicitly.
    @app.context_processor
    def inject_auth_status():
        from app.core.security import is_personal_device, is_logged_in
        from flask import session

        personal = is_personal_device()
        unread_letters = 0
        if personal:
            from app.core.db import get_db
            row = get_db().execute(
                "SELECT COUNT(*) AS n FROM letters WHERE read = 0"
            ).fetchone()
            unread_letters = row["n"]

        return dict(
            is_personal=personal,
            is_logged_in=is_logged_in(),
            current_user=session.get("user_id"),
            unread_letters=unread_letters,
        )

    @app.errorhandler(403)
    def handle_403(e):
        from flask import request, redirect, url_for
        from app.core.security import is_personal_device, is_logged_in
        if request.accept_mimetypes.best_match(["text/html", "application/json"]) == "text/html":
            if is_personal_device():
                return redirect(url_for("remote.index"))
            if is_logged_in():
                return redirect(url_for("auth.root_login"))
            return redirect(url_for("auth.root_login"))
        return "Forbidden", 403

    return app
