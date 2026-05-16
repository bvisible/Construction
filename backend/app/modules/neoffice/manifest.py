"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Module manifest for oe_neoffice — Neoservice cross-cutting extensions.
"""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_neoffice",
    version="1.0.0",
    display_name="Neoffice Extensions",
    display_name_i18n={
        "fr": "Extensions Neoffice",
        "de": "Neoffice-Erweiterungen",
        "it": "Estensioni Neoffice",
    },
    description=(
        "Neoservice cross-cutting extensions for the Neoffice backend. "
        "Hosts the RoomPlan mobile bridge (LiDAR scan import + DXF/IFC "
        "exports), Neoffice mobile-only endpoints, and Neoservice-specific "
        "glue that extends the core backend without belonging to any "
        "regional pack. Regional content stays in swiss_pack/."
    ),
    author="Neoservice (jeremy@neoservice.ai)",
    category="extensions",
    depends=["oe_bim_hub", "oe_projects"],
    auto_install=False,
    enabled=True,
)
