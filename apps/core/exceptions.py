"""
One error shape for every API error:

    {"code": "invalid", "message": "Check the highlighted fields.", "errors": {"email": ["..."]}}

`code` is stable for the web app to branch on; `message` is safe to show; `errors` holds field errors.
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("mannabooks.api")


class BusinessRuleError(exceptions.APIException):
    """A request that is valid but breaks a business rule (e.g. removing the last owner)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "rule"
    default_detail = "This change is not allowed."

    def __init__(self, detail=None, code=None, data: dict | None = None):
        super().__init__(detail, code)
        self.data = data or {}


def _flatten(detail):
    if isinstance(detail, list):
        return [str(item) for item in detail]
    if isinstance(detail, dict):
        return {key: _flatten(value) for key, value in detail.items()}
    return [str(detail)]


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            {"code": "server_error", "message": "Something went wrong on our side. Please try again.", "errors": {}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        errors = _flatten(exc.detail)
        if isinstance(errors, list):
            errors = {"non_field_errors": errors}
        message = errors.get("non_field_errors", ["Check the highlighted fields."])[0] if "non_field_errors" in errors else "Check the highlighted fields."
        response.data = {"code": "invalid", "message": message, "errors": errors}
    else:
        detail = getattr(exc, "detail", "")
        code = detail.code if hasattr(detail, "code") else getattr(exc, "default_code", "error")
        response.data = {"code": str(code), "message": str(detail), "errors": {}}
        if getattr(exc, "data", None):
            response.data["data"] = exc.data  # details the web app can act on (e.g. the date of a closed period)
    return response
