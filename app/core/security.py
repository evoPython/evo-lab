from functools import wraps

from flask import request, current_app, abort


def is_personal_device():

    token = request.cookies.get(
        "evo_device"
    )

    expected = current_app.config.get("DEVICE_TOKEN")

    if not expected:
        return False

    return token == expected


def require_personal_device(view):
    """
    Decorator for routes that must never be reachable by public
    visitors (controls, tools, private APIs, etc).

    Returns 403 instead of rendering/executing anything if the
    request does not carry a valid evo_device cookie.

    This is intentionally simple for now (single shared token via
    /dashboard/pair). It is the seam where real per-device auth
    can be added later without touching every route that uses it.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_personal_device():
            abort(403)
        return view(*args, **kwargs)

    return wrapped
