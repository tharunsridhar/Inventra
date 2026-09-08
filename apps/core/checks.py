"""Guards Phase 6's locking kill-switch: it must be impossible to actually
deploy with INVENTORY_LOCKING_ENABLED=False. The setting exists only to
produce the locked-vs-unlocked comparison in a load test run locally with
DEBUG=True - see docs/v2/LOAD_TEST_RESULTS.md."""

from django.conf import settings
from django.core.checks import Error, register


@register()
def locking_kill_switch_guard(app_configs, **kwargs):
    if settings.INVENTORY_LOCKING_ENABLED or settings.DEBUG:
        return []
    return [
        Error(
            "INVENTORY_LOCKING_ENABLED is False outside of DEBUG.",
            hint="This disables select_for_update() on stock mutations and allows overselling. "
            "It exists only for local load-test comparisons (see docs/v2/LOAD_TEST_RESULTS.md) "
            "and must never be set in a real deployment.",
            id="core.E001",
        )
    ]
