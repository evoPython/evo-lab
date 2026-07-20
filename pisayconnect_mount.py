"""
Loads the pisayconnect-wrapper Flask app — kept as a fully separate,
completely untouched project in ./pisayconnect-wrapper/ — and hands back
a ready-to-mount WSGI app. Nothing inside pisayconnect-wrapper/ is edited.

Two environmental things have to be handled from the outside for it to
work correctly once it's living next to evo-lab instead of standing
alone, and both are done here rather than inside the wrapper's files:

1. Working directory.
   app.py, services/data_cache.py, and services/auth_store.py each open
   sqlite3.connect("data.db") using a *relative* path. Relative paths
   resolve against the process's current working directory, not the
   file's location — so if the combined server is started from the
   evo-lab project root, "data.db" would silently resolve to the wrong
   folder (or create a fresh empty one there). Chdir'ing into the
   wrapper folder once, here, fixes that for the life of the process.
   (evo-lab's own paths are all absolute/BASE_DIR-derived, so this has
   no effect on it.)

2. Session cookie collision.
   Both apps are plain Flask apps with their own secret_key, but
   Flask's default session cookie is always named "session" with path
   "/". Serve them under the same origin unmodified and logging into
   one can silently invalidate the other's session cookie. Giving the
   wrapper app its own cookie name + path here (again, without editing
   its source) keeps the two sessions independent.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PCW_DIR = Path(__file__).resolve().parent / "pisayconnect-wrapper"


class RedirectPrefixFix:
    """
    Wraps a WSGI app mounted at `prefix` and rewrites any outgoing
    root-relative Location header (e.g. from a hardcoded
    `redirect("/app/dashboard")` inside the wrapped app) so it comes
    back prefixed correctly (`/pisayconnect/app/dashboard`) instead of
    404ing against evo-lab's own routes.

    DispatcherMiddleware alone can't fix this: it rewrites SCRIPT_NAME
    so url_for(...)-based redirects pick up the prefix automatically,
    but a literal string like redirect("/app/dashboard") never
    consults SCRIPT_NAME at all. This middleware catches those at the
    WSGI layer, on the way out, without touching the wrapped app's
    source.
    """

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        def fixed_start_response(status, headers, exc_info=None):
            new_headers = []
            for name, value in headers:
                if name.lower() == "location":
                    parsed = urlsplit(value)
                    path = parsed.path
                    already_prefixed = (
                        path == self.prefix or path.startswith(self.prefix + "/")
                    )
                    if path.startswith("/") and not already_prefixed:
                        value = urlunsplit(
                            parsed._replace(path=self.prefix + path)
                        )
                new_headers.append((name, value))
            return start_response(status, new_headers, exc_info)

        return self.wsgi_app(environ, fixed_start_response)


class StaticJsPathPrefixFix:
    r"""
    Rewrites hardcoded root-relative paths inside the wrapper's
    responses — things like fetch(`/api/view/...`), fetch(`/bookmark/...`),
    fetch(`/download/...`), and the `/app/...` strings used to build
    pushState URLs for the SPA router, plus the matching `href="/app/..."`
    links, hidden-input values, and Jinja-rendered back-URLs in the
    server-rendered HTML templates.

    Those are plain string literals in static/js/*.js (never rendered
    through Jinja) or Jinja output baked into the final HTML before it
    ever reaches url_for()/SCRIPT_NAME — so neither can be fixed the way
    server-rendered `url_for(...)` links normally would be. Left alone,
    the browser resolves them against the real origin root
    (e.g. evo.ftp.sh/api/...) instead of /pisayconnect/api/..., which is
    exactly the "JSON.parse: unexpected character" / OpaqueResponseBlocking
    symptom for fetches, and a 404-or-wrong-page for the `<a href>` case
    — clicking a sidebar link or a "back to classwall" link lands on
    evo-lab's own unprefixed /app/... route instead of the wrapper's.

    This rewrites the response *bytes* for JS, HTML, and JSON responses,
    on the way out, so the files on disk are never touched. It only
    matches `"/api/`, `"/app/`, `"/bookmark/`, `"/download/` style
    literals (quote or backtick, optionally JSON-escaped as `\"`,
    immediately followed by the prefix and a trailing slash), so it
    can't accidentally mangle unrelated text.

    JSON matters here because most of the SPA's actual navigation never
    touches a full HTML page at all: /api/view/<view_name> (and the
    bulletin/post/leave-pass pagination and search endpoints) respond
    with `jsonify({"html": "<a href=\"/app/classwall\">...", ...})` —
    the rendered view's HTML travels JSON-encoded, so on the wire every
    `"` around an href becomes `\"`. Fixing only HTML and JS responses
    left every one of these dynamically-loaded views still full of
    unprefixed `/app/...` links, which is why dashboard-internal links
    kept pointing at `/app/...` even after the initial page load was
    correct.

    Two spots in app.js are NOT plain `"/app/..."` string literals and
    so the pattern above intentionally skips them — but both turned out
    to actually break navigation, not just cosmetically:

    1. parseAppPath()'s prefix-stripping step uses a *regex literal*,
       not a string: `pathname.replace(/^\/app\/?/, "")`. Once this
       file is served under /pisayconnect, the browser's real pathname
       is `/pisayconnect/app/...`, that regex no longer matches, the
       prefix never gets stripped, every `if (path === "...")` branch
       in parseAppPath() falls through, and it silently returns the
       `{ view: "dashboard" }` fallback. Since navigate() is called
       with the real prefixed pathname on every page load
       (DOMContentLoaded), every back/forward (popstate), and every
       school-year <select> change, this is what was causing "school
       year list sometimes doesn't show" (misfires on hydration) and
       "picking a school year redirects to /app/dashboard and doesn't
       save" (misfires on the select's own navigate() call) — 100%
       reproducible for the latter.

    2. isSpaLink() checks `url.pathname.startsWith("/app")` — a plain
       string, but with no trailing slash, so it doesn't match this
       rewrite's `/(app|api|bookmark|download)/` pattern either. This
       one only matters *because* of the HTML fix above: once template
       hrefs are correctly rewritten to `/pisayconnect/app/...`,
       isSpaLink's check has to expect that same prefix too, or every
       sidebar/nav link click stops being recognized as an in-app
       link and falls back to a full page load instead of an SPA
       transition (still a real destination, just not the smooth one).

    _REGEX_LITERAL_PATTERN and _BARE_STRING_PATTERN below handle both
    as a second, JS-only pass: they match the exact regex-literal
    source `/^\/app\/?/` and the exact quoted string `"/app"` (in any
    of `"`, `'`, `` ` ``), and nothing else — so they can't accidentally
    touch unrelated text.
    """

    # Matches a literal quote/backtick OR a JSON-escaped quote (\")
    # immediately followed by /app/, /api/, /bookmark/, or /download/.
    # The optional leading backslash is what makes this also work
    # inside JSON responses: endpoints like /api/view/<view_name> (and
    # the bulletin/post/leave-pass pagination and search endpoints)
    # return `jsonify({"html": "<a href=\"/app/classwall\">...", ...})`
    # — the rendered HTML travels JSON-encoded, so every `"` around an
    # href becomes `\"` on the wire. Most of the app's actual in-page
    # navigation happens through exactly these endpoints (that's how
    # the SPA swaps view content without a full reload), so without
    # this the dashboard's own links stayed unprefixed even after HTML
    # and JS responses were fixed directly.
    _PATTERN = re.compile(rb'(\\?["\'`])/(app|api|bookmark|download)/')

    # Matches the literal regex source `/^\/app\/?/` used to strip the
    # /app prefix in parseAppPath().
    _REGEX_LITERAL_PATTERN = re.compile(rb'/\^\\/app\\/\?/')

    # Matches the bare, trailing-slash-less `"/app"` (or '/app' or
    # `/app`) used in isSpaLink()'s startsWith() check.
    _BARE_STRING_PATTERN = re.compile(rb'(["\'`])/app\1')

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix_bytes = prefix.encode("utf-8")

    # Headers that would let Flask's static handler short-circuit with a
    # 304 Not Modified (and no body) using an ETag/Last-Modified computed
    # from the untouched file on disk — which would mean the browser just
    # keeps reusing whatever copy it cached *before* this rewrite existed,
    # forever, since the file itself never changes. Stripping these from
    # the incoming environ forces a full, fresh 200 every time, so the
    # rewrite below always actually runs.
    _CONDITIONAL_HEADERS = ("HTTP_IF_NONE_MATCH", "HTTP_IF_MODIFIED_SINCE")

    def __call__(self, environ, start_response):
        environ = {
            k: v for k, v in environ.items() if k not in self._CONDITIONAL_HEADERS
        }

        captured = {}

        def capturing_start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info
            return lambda data: None

        app_iter = self.wsgi_app(environ, capturing_start_response)

        content_type = ""
        for name, value in captured["headers"]:
            if name.lower() == "content-type":
                content_type = value.lower()
                break

        is_js = "javascript" in content_type
        is_html = "html" in content_type
        is_json = "json" in content_type
        if not is_js and not is_html and not is_json:
            start_response(captured["status"], captured["headers"], captured["exc_info"])
            return app_iter

        body = b"".join(app_iter)
        if hasattr(app_iter, "close"):
            app_iter.close()

        prefix_stripped = self.prefix_bytes.lstrip(b"/")

        new_body = self._PATTERN.sub(
            lambda m: m.group(1) + b"/" + prefix_stripped + b"/" + m.group(2) + b"/",
            body,
        )

        # The regex-literal and bare-string fixes only apply to JS
        # source (they're not valid/meaningful things to rewrite inside
        # rendered HTML), so keep them JS-only.
        if is_js:
            new_body = self._REGEX_LITERAL_PATTERN.sub(
                b"/^\\/" + prefix_stripped + b"\\/app\\/?/",
                new_body,
            )
            new_body = self._BARE_STRING_PATTERN.sub(
                lambda m: m.group(1) + b"/" + prefix_stripped + b"/app" + m.group(1),
                new_body,
            )

        # Also stop the browser itself from caching this so aggressively
        # that it never even asks the server again — otherwise the next
        # deploy could get stuck behind a stale local copy the same way.
        drop = {"content-length", "etag", "last-modified", "cache-control", "expires"}
        new_headers = [
            (name, value) for name, value in captured["headers"]
            if name.lower() not in drop
        ]
        new_headers.append(("Content-Length", str(len(new_body))))
        new_headers.append(("Cache-Control", "no-store"))

        start_response(captured["status"], new_headers, captured["exc_info"])
        return [new_body]


def load_pisayconnect_app(mount_prefix="/pisayconnect"):
    # So the wrapper's own `from services.xxx import ...` imports resolve.
    if str(PCW_DIR) not in sys.path:
        sys.path.insert(0, str(PCW_DIR))

    # So its relative "data.db" sqlite3.connect() calls land in the
    # right folder regardless of where the combined server was started.
    os.chdir(PCW_DIR)

    # Loaded under a private module name (NOT "app") so it can't clash
    # with evo-lab's own top-level `app` package of the same name.
    spec = importlib.util.spec_from_file_location(
        "pisayconnect_wrapper_app", PCW_DIR / "app.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["pisayconnect_wrapper_app"] = module
    spec.loader.exec_module(module)

    pcw_app = module.app
    pcw_app.config["SESSION_COOKIE_NAME"] = "pisayconnect_session"
    pcw_app.config["SESSION_COOKIE_PATH"] = mount_prefix

    wrapped = StaticJsPathPrefixFix(pcw_app, mount_prefix)
    wrapped = RedirectPrefixFix(wrapped, mount_prefix)
    return wrapped
