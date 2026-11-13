"""Request-ID assignment + propagation (Phase 1).

Clients may send X-Request-ID (the frontend does); otherwise one is minted.
The ID is echoed on every response and available as g.request_id for logs.
"""

import uuid

from flask import g, request


def register_request_id(app) -> None:
    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]

    @app.after_request
    def _expose_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response
