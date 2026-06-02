"""Event subscriptions for the costmodel_typed module.

Module loader auto-imports this file at startup (cf. core/module_loader.py
``_load_module``). It is intentionally minimal for now: downstream modules
(e.g. the private ``oe_protti`` module) subscribe to the events PUBLISHED
by ``service.py`` rather than to events handled here.

This file exists so the module loader executes its top-level statements at
boot — any future internal subscription (for example: log statistics on
component creation) would land here.
"""

import logging

logger = logging.getLogger(__name__)
logger.debug("oe_costmodel_typed events module loaded (no internal subscriptions)")
