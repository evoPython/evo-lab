import hashlib
from functools import wraps

from flask import session, abort, current_app


def _root_password_fingerprint():
    """
    Short, non-reversible fingerprint of the currently configured root
    password. Used to tie a root session to the password that was active
    when the user logged in, so that changing ROOT_PASSWORD in .env (and
    restarting the app) invalidates any sessions issued under the old
    password, even if that browser never explicitly logs out.
    """
    expected = current_app.config.get("ROOT_PASSWORD") or ""
    return hashlib.sha256(expected.encode("utf-8")).hexdigest()


def is_personal_device():
    """
    Kept as the single gate for laptop-facing "remote access" features
    (controls, tools, niri, media, launcher). Now backed by the root
    login session instead of a device-pairing cookie.
    """
    if not session.get("is_root"):
        return False

    # If the root password has since changed, this session was issued
    # under a stale password and should no longer grant access.
    if session.get("root_pw_fp") != _root_password_fingerprint():
        session.pop("is_root", None)
        session.pop("root_pw_fp", None)
        return False

    return True


def require_personal_device(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_personal_device():
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def is_logged_in():
    """Personal account login (username/password), separate from root."""
    return "user_id" in session


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            from flask import redirect, url_for
            return redirect(url_for("auth.login"))
        # Keep presence fresh for the cross-remote "who's online" list.
        from app.auth.users import touch_last_seen
        touch_last_seen(session["user_id"])
        return view(*args, **kwargs)

    return wrapped
