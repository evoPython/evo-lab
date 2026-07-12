from flask import Blueprint, render_template, request, redirect, url_for, session, current_app

from app.auth import users
from app.core.security import is_personal_device, is_logged_in, _root_password_fingerprint


auth = Blueprint("auth", __name__, url_prefix="/auth")


# --- Personal login (username + password, can self-register) ---

@auth.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        action = request.form.get("action")

        if not username or not password:
            error = "Username and password are required."
        elif action == "register":
            if users.get_user(username):
                error = "That username is already taken."
            else:
                users.create_user(username, password)
                session["user_id"] = username
                users.touch_last_seen(username)
                return redirect(url_for("cross_remote.index"))
        else:
            user = users.verify_user(username, password)
            if user:
                session["user_id"] = username
                users.touch_last_seen(username)
                return redirect(url_for("cross_remote.index"))
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@auth.route("/logout")
def logout():
    """
    Universal logout: clears both the personal account session and the
    root session in one go, so there's no leftover half-logged-in state
    (e.g. dashboard topbar showing on the home page after "logging out").
    """
    session.pop("user_id", None)
    session.pop("is_root", None)
    session.pop("root_pw_fp", None)
    return redirect(url_for("portfolio.home"))


# --- Root login (single shared password from .env, unlocks remote access) ---

@auth.route("/root", methods=["GET", "POST"])
def root_login():
    if is_personal_device():
        return redirect(url_for("remote.index"))

    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        expected = current_app.config.get("ROOT_PASSWORD")

        if expected and password == expected:
            session["is_root"] = True
            session["root_pw_fp"] = _root_password_fingerprint()
            return redirect(url_for("remote.index"))

        error = "Incorrect root password."

    return render_template("root_login.html", error=error)


@auth.route("/root/logout")
def root_logout():
    """
    Kept as an alias of the universal logout for any old links/bookmarks.
    Also clears the personal session so root logout can't leave a
    half-logged-in state either.
    """
    return logout()
