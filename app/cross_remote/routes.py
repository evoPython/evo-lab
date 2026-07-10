from flask import Blueprint, render_template, request, jsonify, session

from app.core.security import require_login
from app.auth.users import list_online
from app.cross_remote import store


cross_remote = Blueprint("cross_remote", __name__, url_prefix="/cross-remote")


@cross_remote.route("/")
@require_login
def index():
    return render_template("cross_remote.html", me=session["user_id"])


@cross_remote.route("/api/online")
@require_login
def api_online():
    me = session["user_id"]
    return jsonify([u for u in list_online() if u != me])


@cross_remote.route("/api/messages/send", methods=["POST"])
@require_login
def api_send():
    data = request.get_json(silent=True) or {}
    to = (data.get("to") or "").strip()
    body = (data.get("body") or "").strip()
    if not to or not body:
        return jsonify({"status": "error", "message": "Missing 'to' or 'body'"}), 400
    store.send_message(session["user_id"], to, body)
    return jsonify({"status": "ok"})


@cross_remote.route("/api/messages")
@require_login
def api_messages():
    other = request.args.get("with", "")
    since_id = int(request.args.get("since_id", 0))
    if not other:
        return jsonify({"status": "error", "message": "Missing 'with'"}), 400
    return jsonify(store.get_conversation(session["user_id"], other, since_id))


@cross_remote.route("/api/call/start", methods=["POST"])
@require_login
def api_call_start():
    data = request.get_json(silent=True) or {}
    to = (data.get("to") or "").strip()
    if not to:
        return jsonify({"status": "error", "message": "Missing 'to'"}), 400
    call_id = store.create_call(session["user_id"], to)
    return jsonify({"status": "ok", "call_id": call_id})


@cross_remote.route("/api/call/incoming")
@require_login
def api_call_incoming():
    return jsonify(store.incoming_calls(session["user_id"]))


@cross_remote.route("/api/call/state")
@require_login
def api_call_state():
    call_id = request.args.get("call_id", "")
    call = store.get_call(call_id)
    if not call:
        return jsonify({"status": "error", "message": "Unknown call"}), 404
    return jsonify(call)


@cross_remote.route("/api/call/accept", methods=["POST"])
@require_login
def api_call_accept():
    data = request.get_json(silent=True) or {}
    store.set_call_status(data.get("call_id", ""), "active")
    return jsonify({"status": "ok"})


@cross_remote.route("/api/call/decline", methods=["POST"])
@require_login
def api_call_decline():
    data = request.get_json(silent=True) or {}
    store.set_call_status(data.get("call_id", ""), "declined")
    return jsonify({"status": "ok"})


@cross_remote.route("/api/call/end", methods=["POST"])
@require_login
def api_call_end():
    data = request.get_json(silent=True) or {}
    store.set_call_status(data.get("call_id", ""), "ended")
    return jsonify({"status": "ok"})


@cross_remote.route("/api/call/signal", methods=["POST"])
@require_login
def api_call_signal():
    data = request.get_json(silent=True) or {}
    call_id = data.get("call_id", "")
    kind = data.get("kind", "")
    payload = data.get("data", "")
    if not (call_id and kind and payload):
        return jsonify({"status": "error", "message": "Missing fields"}), 400
    store.add_signal(call_id, session["user_id"], kind, payload)
    return jsonify({"status": "ok"})


@cross_remote.route("/api/call/signals")
@require_login
def api_call_signals():
    call_id = request.args.get("call_id", "")
    since_id = int(request.args.get("since_id", 0))
    return jsonify(store.get_signals(call_id, session["user_id"], since_id))
