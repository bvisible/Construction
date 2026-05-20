"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Event wiring for the `neoffice` module. The module loader auto-imports this
file when the module is loaded; importing the bridge subpackage registers
its EventBus subscriptions at import time.
"""

from app.modules.neoffice.bridge import events as _bridge_events  # noqa: F401
