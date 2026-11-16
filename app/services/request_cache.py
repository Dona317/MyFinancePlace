"""A dict that lives as long as the current HTTP request (empty and throwaway outside a request)."""
from flask import has_request_context, request


def cache() -> dict:
    if not has_request_context():
        return {}
    return request.__dict__.setdefault("_mfp_cache", {})


def data() -> dict:
    """Like cache(), for what was read from the database: forgotten as soon as the request writes to it or rolls
    back (extensions._forget_what_was_read), so a page that saves and then shows never reads its own past."""
    return cache().setdefault("_data", {})


_versions: dict[str | None, int] = {}  # database name → how many writes this process sent to it


def wrote(database: str | None) -> None:
    """A statement that may have changed `database` (or a rollback): what the request read is forgotten."""
    _versions[database] = _versions.get(database, 0) + 1
    if has_request_context():
        cache().pop("_data", None)


def version(database: str | None) -> int:
    """A number that changes at every write of this process to a database: what a longer-lived cache is keyed on."""
    return _versions.get(database, 0)


def clear() -> None:
    """Forget what this request cached (another client's archive was opened)."""
    cache().clear()
