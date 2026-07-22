from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

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

    run_simple(
        "0.0.0.0",
        5000,
        application,
        threaded=True,
    )
