"""JSON error handlers (Phase 1).

flask-openapi3 keeps owning request-validation (422) responses. These
handlers cover routing/server failures so API consumers never get HTML.
"""

import logging

from common.responses import error_response

logger = logging.getLogger(__name__)


def register_error_handlers(app) -> None:
    @app.errorhandler(404)
    def _not_found(_e):
        return error_response("Not Found", "The requested URL was not found.", 404)

    @app.errorhandler(405)
    def _method_not_allowed(_e):
        return error_response("Method Not Allowed", "The method is not allowed for this URL.", 405)

    @app.errorhandler(500)
    def _internal(_e):
        logger.exception("Unhandled exception (request_id=%s)", _request_id_safe())
        return error_response("Internal Server Error", "An unexpected error occurred.", 500)


def _request_id_safe() -> str:
    try:
        from flask import g

        return getattr(g, "request_id", "-")
    except Exception:  # noqa: BLE001 -- logging helper must never raise
        return "-"
