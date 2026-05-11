"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.

Module manifest for oe_swiss_pack.
"""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_swiss_pack",
    version="1.0.0",
    display_name="Regional Pack — Switzerland (CH)",
    display_name_i18n={
        "fr": "Pack régional — Suisse (CH)",
        "de": "Regionalpaket — Schweiz (CH)",
        "it": "Pacchetto regionale — Svizzera (CH)",
    },
    description=(
        "Swiss construction standards: CFC (SIA 506 500), eBKP-H/eBKP-T "
        "(SIA 506 511/512), NPK Catalogue des articles normalisés (CRB), "
        "SIA norms (102/103/108/118/122-126), TVA Suisse 2024 (8.1%/2.6%/3.8%), "
        "contract types (Forfait/Régie/Unité), CN 2026-2031 labor classes, "
        "OFAS social charges, SUVA class 41A, KBOB indices reference. "
        "Trilingual support FR/DE/IT (Swiss Romandy / Swiss German / Ticino)."
    ),
    author="Neoservice (jeremy@neoservice.ai)",
    category="regional",
    depends=[],
    auto_install=False,
    enabled=True,
)
