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

    @app.errorhandler(Exception)
    def _unhandled(e):
        """Surface target-database failures instead of a generic 500.

        Driver errors (unreachable host, refused credentials, timeout) are
        actionable for the user, so the reason is returned instead of being
        swallowed. Genuinely unexpected exceptions keep the generic message and
        are logged with a full traceback.
        """
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e

        if _is_target_db_error(e):
            logger.warning("Target database error (request_id=%s): %s", _request_id_safe(), e)
            return error_response("Database unreachable", str(e), 502)

        logger.exception("Unhandled exception (request_id=%s)", _request_id_safe())
        return error_response("Internal Server Error", "An unexpected error occurred.", 500)

    _register_validation_error_handler(app)


def _register_validation_error_handler(app) -> None:
    """Sanitize 422 validation responses so they never echo secrets.

    flask-openapi3 answers a schema violation with a pydantic error list.
    By default each entry contains ``input`` - the rejected value - which
    would send the plaintext password back to the client in the response
    body.

    flask-openapi3 exposes ``validation_error_callback`` as the supported
    hook for this, so we replace it with a sanitizer that drops the
    offending values and returns the standard error envelope with a
    human-readable reason.
    """
    try:
        from flask import jsonify
    except ImportError:  # pragma: no cover
        return

    def _validation_error_callback(exc):
        issues = []
        reasons = []
        for issue in exc.errors():
            sanitized = {k: v for k, v in issue.items() if k != "input"}
            ctx = issue.get("ctx")
            reason = ctx.get("error") if isinstance(ctx, dict) else None
            if not reason:
                reason = issue.get("msg", "")
            # Pydantic prefixes custom validators with "Value error, " and
            # stores the raised exception object in ctx, so normalise both.
            reason = str(reason).replace("Value error, ", "")

            sanitized = {
                "type": issue.get("type"),
                "loc": issue.get("loc"),
                "msg": reason,
            }
            if issue.get("url"):
                sanitized["url"] = issue["url"]
            if isinstance(ctx, dict):
                sanitized["ctx"] = {k: str(v) for k, v in ctx.items()}

            reasons.append(reason)
            issues.append(sanitized)

        message = "; ".join(reasons) if reasons else "Request validation failed."
        response = jsonify(
            {
                "success": False,
                "error": "Validation failed",
                "message": message,
                "details": issues,
            }
        )
        response.status_code = 422
        return response

    app.validation_error_callback = _validation_error_callback


def _is_target_db_error(exc: Exception) -> bool:
    """True for SQLAlchemy/driver errors raised while talking to a user DB."""
    try:
        from sqlalchemy.exc import SQLAlchemyError

        return isinstance(exc, SQLAlchemyError)
    except Exception:  # noqa: BLE001 -- never let the classifier raise
        return False


def _request_id_safe() -> str:
    try:
        from flask import g

        return getattr(g, "request_id", "-")
    except Exception:  # noqa: BLE001 -- logging helper must never raise
        return "-"
