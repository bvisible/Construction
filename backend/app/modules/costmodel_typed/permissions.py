"""Typed Cost Components & Yield Library permission definitions."""

from app.core.permissions import Role, permission_registry


def register_costmodel_typed_permissions() -> None:
    """Register permissions for the costmodel_typed module."""
    permission_registry.register_module_permissions(
        "costmodel_typed",
        {
            "costmodel_typed.read": Role.VIEWER,
            "costmodel_typed.write": Role.EDITOR,
            "costmodel_typed.manage": Role.MANAGER,
        },
    )
