"""
Centralized request logging.

Hooked in once from the app factory (before_request/after_request/
teardown_request) — every route in every blueprint gets logged
automatically. No per-route changes needed; if you add a new
blueprint, it's covered for free.
"""

import logging
import sys
import time

from flask import g, request

# Paths under these prefixes are skipped entirely — noisy, low-signal
# stuff like static assets or presence polling. Add to this as needed.
QUIET_PREFIXES = (
    "/static/",
)

RESET = "\033[0m"
DIM = "\033[2m"

METHOD_COLORS = {
    "GET": "\033[34m",     # blue
    "POST": "\033[35m",    # magenta
    "PUT": "\033[33m",     # yellow
    "PATCH": "\033[33m",   # yellow
    "DELETE": "\033[31m",  # red
}


def _status_color(status):
    if status < 300:
        return "\033[32m"  # green
    if status < 400:
        return "\033[36m"  # cyan
    if status < 500:
        return "\033[33m"  # yellow
    return "\033[1;31m"    # bold red


def _use_color():
    return sys.stdout.isatty()


def _human_size(n):
    if n is None:
        return "-"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024


logger = logging.getLogger("evo.requests")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False


def start_timer():
    g._req_start = time.perf_counter()


def log_request(response):
    path = request.path
    if path.startswith(QUIET_PREFIXES):
        return response

    elapsed_ms = (time.perf_counter() - getattr(g, "_req_start", time.perf_counter())) * 1000
    method = request.method
    status = response.status_code
    size = _human_size(response.calculate_content_length())
    clock = time.strftime("%H:%M:%S")

    if _use_color():
        m_color = METHOD_COLORS.get(method, "\033[37m")
        s_color = _status_color(status)
        line = (
            f"{DIM}{clock}{RESET} "
            f"{m_color}{method:<6}{RESET} "
            f"{s_color}{status}{RESET} "
            f"{path} "
            f"{DIM}{elapsed_ms:6.1f}ms {size:>8}  <- {request.remote_addr}{RESET}"
        )
    else:
        line = f"{clock} {method:<6} {status} {path} {elapsed_ms:.1f}ms {size} <- {request.remote_addr}"

    logger.info(line)
    return response


def log_exception(exc):
    if exc is None:
        return
    prefix = "\033[1;31m!! EXCEPTION\033[0m" if _use_color() else "!! EXCEPTION"
    logger.info(f"{prefix} {request.method} {request.path}: {exc}")
