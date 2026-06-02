"""Typed cost components & yield library manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_costmodel_typed",
    version="0.1.0",
    display_name="Typed Cost Components & Yield Library",
    description=(
        "Adds a typed component layer (labor, machine, material, internal loc, "
        "external margin, subcontractor margin, misc, transport, fg_admin) on "
        "top of Cost Spine CostLines, plus a project-scoped (or global) yield "
        "library tracking productivity rates (U/h). Downstream modules subscribe "
        "to the published events to inject domain-specific pricing rules."
    ),
    author="OpenEstimate Core Team",
    category="extensions",
    depends=["oe_costmodel", "oe_boq", "oe_projects"],
    auto_install=True,
    enabled=True,
)
