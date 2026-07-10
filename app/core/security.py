from functools import wraps

from flask import session, abort


def is_personal_device():
    """
    Kept as the single gate for laptop-facing "remote access" features
    (controls, tools, niri, media, launcher). Now backed by the root
    login session instead of a device-pairing cookie.
    """
    return bool(session.get("is_root"))


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
