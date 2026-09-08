"""DRF's ScopedRateThrottle keys off a single `view.throttle_scope`
attribute, which doesn't fit a ViewSet whose different actions (list vs
create vs a custom @action like /receive) need different rates. This mixin
maps `self.action` to a scope per-request before delegating to DRF's own
get_throttles(), so one ViewSet can have list/retrieve throttled as "read"
while its write actions are throttled separately, without needing a
separate ViewSet class per rate."""

class ScopedByActionThrottleMixin:
    """Mix in alongside a DRF ViewSet (which provides self.action)."""

    #: {action_name: scope}; falls back to default_throttle_scope for any
    #: action not listed (e.g. a ViewSet's default `list`/`retrieve` don't
    #: need to be repeated in every subclass if they all map to "read").
    action_throttle_scopes: dict[str, str] = {}
    default_throttle_scope = "read"

    def get_throttles(self):
        self.throttle_scope = self.action_throttle_scopes.get(self.action, self.default_throttle_scope)
        return super().get_throttles()
