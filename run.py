from waitress import serve
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app import create_app
from pisayconnect_mount import load_pisayconnect_app


app = create_app()

# pisayconnect-wrapper stays a fully separate project (its own
# templates/, static/, services/, data.db) — it's just mounted at
# /pisayconnect at the WSGI level, not merged into evo-lab's folders.
pisayconnect_app = load_pisayconnect_app()

application = DispatcherMiddleware(app, {
    "/pisayconnect": pisayconnect_app,
})


if __name__ == "__main__":

    # Werkzeug's dev server (run_simple) is a bare-bones HTTP/1.1
    # implementation — fine when every request comes in already
    # normalized by a proxy (e.g. the Tailscale path), but it doesn't
    # reliably handle the raw HTTP/1.1 behavior of real mobile browsers
    # talking to it directly over LAN (keep-alive reuse, slow/flaky
    # WiFi writes, `Expect: 100-continue`, etc.) — uploads in
    # particular would hang mid-request and never complete. Waitress is
    # a small, pure-Python, production-grade WSGI server that handles
    # all of that correctly, with no other code changes required.
    serve(
        application,
        host="0.0.0.0",
        port=5000,
        threads=32,
    )
