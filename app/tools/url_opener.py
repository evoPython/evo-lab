import shutil
import subprocess
from urllib.parse import urlparse


ALLOWED_SCHEMES = {"http", "https"}


class InvalidURLError(Exception):
    """Raised when a submitted URL fails validation."""


def validate_url(url):

    url = (url or "").strip()

    if not url:
        raise InvalidURLError("No URL provided")

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError("URL must start with http:// or https://")

    if not parsed.netloc:
        raise InvalidURLError("URL must include a valid host")

    return url


def open_url(url):
    """
    Opens a URL in the laptop's default browser via xdg-open.

    Uses subprocess.Popen with a list of arguments (never shell=True
    and never string interpolation), so the input can't be used to
    inject shell commands -- at worst an invalid value just fails to
    open as a URL.
    """

    url = validate_url(url)

    if shutil.which("xdg-open") is None:
        raise InvalidURLError("xdg-open is not available on this system")

    subprocess.Popen(["xdg-open", url])

    return url
