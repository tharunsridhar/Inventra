"""Version-counter cache invalidation (see docs/v2/adr/0001-cache-invalidation.md).

Enumerating and deleting individual cache keys on every stock mutation
doesn't scale and it's easy to miss one (a new query-param combination, a
new report). Instead each namespace has one version integer in the cache;
every cached key for that namespace embeds the version it was written
under, and invalidation is a single `cache.incr()` - every previously
cached key for the namespace is now unreachable (orphaned under an old
version number) and expires naturally by TTL. No key enumeration, no risk
of a missed delete.
"""

import hashlib
from functools import wraps

import structlog
from django.core.cache import cache
from rest_framework.response import Response

logger = structlog.get_logger(__name__)

VERSION_KEY_TEMPLATE = "cache:version:{namespace}"
DEFAULT_TTL = 300


def get_version(namespace: str) -> int:
    key = VERSION_KEY_TEMPLATE.format(namespace=namespace)
    version = cache.get(key)
    if version is None:
        cache.set(key, 1, timeout=None)
        return 1
    return version


def bump_version(namespace: str) -> None:
    """Orphan every key currently cached under this namespace. Call this
    from inside transaction.on_commit(...), never inline - invalidating on
    the basis of a change that then rolls back would serve a phantom
    write to the next reader."""
    key = VERSION_KEY_TEMPLATE.format(namespace=namespace)
    try:
        cache.incr(key)
    except ValueError:
        # Nothing was ever cached under this namespace (key doesn't exist
        # yet) - jump straight past the version get_version() would hand
        # out next, so no key computed just before this call can survive.
        cache.set(key, 2, timeout=None)


def _cache_key(namespace: str, endpoint: str, request) -> str:
    version = get_version(namespace)
    # Scoped by user id + role, not just query params: a cache that leaks
    # one user's data to another - or an Employee's request key colliding
    # with an Admin-scoped response - is worse than no cache at all.
    scope = f"{request.user.pk}:{request.user.role}"
    params = request.GET.urlencode()
    digest = hashlib.sha256(f"{scope}:{params}".encode()).hexdigest()[:16]
    return f"{namespace}:v{version}:{endpoint}:{digest}"


def cached_response(namespace: str, ttl: int = DEFAULT_TTL):
    """Method decorator for a DRF view's `get()`. Caches only 2xx responses,
    keyed per namespace-version + requesting user + query params. Adds
    X-Cache: HIT/MISS to every response it handles."""

    def decorator(view_method):
        @wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            endpoint = self.__class__.__name__
            key = _cache_key(namespace, endpoint, request)
            cached = cache.get(key)
            if cached is not None:
                # One log line per request, hit or miss - a log aggregator
                # computes the hit/miss ratio per endpoint from these over
                # time; nothing needs to be tallied in-process here.
                logger.info("cache_lookup", endpoint=endpoint, outcome="hit")
                response = Response(cached["data"], status=cached["status"])
                response["X-Cache"] = "HIT"
                return response

            response = view_method(self, request, *args, **kwargs)
            if 200 <= response.status_code < 300:
                cache.set(key, {"data": response.data, "status": response.status_code}, timeout=ttl)
            logger.info("cache_lookup", endpoint=endpoint, outcome="miss")
            response["X-Cache"] = "MISS"
            return response

        return wrapper

    return decorator
