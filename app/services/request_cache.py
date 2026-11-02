"""A dict that lives as long as the current HTTP request (empty and throwaway outside a request)."""
from flask import has_request_context, request


def cache() -> dict:
    if not has_request_context():
        return {}
    return request.__dict__.setdefault("_mfp_cache", {})


def clear() -> None:
    """Forget what this request cached (another client's archive was opened)."""
    cache().clear()
