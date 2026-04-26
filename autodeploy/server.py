from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path

from flask import Flask, Response, jsonify, request

from autodeploy import pipeline
from autodeploy.config import ConfigError, load as load_config

log = logging.getLogger("autodeploy.server")

app = Flask(__name__)

# silence Flask's default request logs; autodeploy has its own
log_handler = logging.getLogger("werkzeug")
log_handler.setLevel(logging.ERROR)


def _secret() -> bytes:
    s = os.environ.get("WEBHOOK_SECRET", "")
    if not s:
        raise RuntimeError("WEBHOOK_SECRET is not set")
    return s.encode()


def _repo_path() -> Path:
    p = os.environ.get("REPO_PATH", "")
    if not p:
        raise RuntimeError("REPO_PATH is not set")
    return Path(p)


def _verify_signature(body: bytes, header: str | None) -> bool:
    if not header:
        return False
    if not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(_secret(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


@app.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["POST"])
def webhook() -> tuple[Response, int]:
    body = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256")

    try:
        secret = _secret()
    except RuntimeError as e:
        log.error("config error: %s", e)
        return jsonify({"error": str(e)}), 500

    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not sig or not hmac.compare_digest(expected, sig):
        log.warning("invalid or missing signature")
        return jsonify({"error": "invalid signature"}), 403

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid JSON"}), 400

    try:
        repo_path = _repo_path()
        config = load_config(repo_path)
    except (RuntimeError, ConfigError) as e:
        log.error("config error: %s", e)
        return jsonify({"error": str(e)}), 500

    ref = payload.get("ref", "")
    expected_ref = f"refs/heads/{config.branch}"
    if ref != expected_ref:
        log.info("ignoring push to %s (watching %s)", ref, expected_ref)
        return jsonify({"status": "ignored", "ref": ref}), 200

    log.info("deploying from webhook, ref=%s", ref)
    msgs: list[str] = []
    entry = pipeline.run(config, repo_path, trigger="webhook", log_fn=msgs.append)

    for m in msgs:
        log.info(m)

    if entry["result"] in ("success", "rolled_back"):
        return jsonify({"status": entry["result"]}), 200
    return jsonify({"status": "failed"}), 500


def run(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    app.run(host=host, port=port, debug=debug, use_reloader=False)
