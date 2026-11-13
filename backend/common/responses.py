"""Standard JSON envelopes (Phase 1).

Existing routes keep their historical shapes until the Phase 5 contract
lock; new endpoints and error handlers must use these helpers.
"""

from typing import Any

from flask import g, jsonify


def _request_id() -> str | None:
    try:
        return g.get("request_id")  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001 -- safe fallback outside request context
        return None


def success_response(data: Any = None, message: str = "ok", status: int = 200):
    payload: dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    rid = _request_id()
    if rid:
        payload["request_id"] = rid
    return jsonify(payload), status


def error_response(error: str, message: str = "", status: int = 400, details: Any = None):
    payload: dict[str, Any] = {"success": False, "error": error}
    if message:
        payload["message"] = message
    if details is not None:
        payload["details"] = details
    rid = _request_id()
    if rid:
        payload["request_id"] = rid
    return jsonify(payload), status
