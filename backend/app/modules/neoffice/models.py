"""NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.

Text catalogue: the Swiss CAN / NPK way of writing a tender position.

Why this is not the existing cost catalogue
-------------------------------------------
``oe_costs_item.rate`` is ``nullable=False``: every row in a cost catalogue is
a PRICED article. A CAN catalogue is the opposite — it is a library of position
TEXTS, and the price only appears further down, if at all:

    135.046  Fourniture et mise en place d'un béton de propreté sur fond de
             terrassement, surface prête à recevoir les armatures.
      .01    Sous radier
             Béton CP 150 0/32
             Épaisseur env. 5 cm                                        m2
      .02    Sous radier
             Béton caverneux CP 150
             Épaisseur env. 10 cm                                       m2

The parent (135.046) carries the wording and no unit at all. Only the
sub-positions are measurable, and each may be linked to its own assembly so
that picking the text in a BOQ brings the priced recipe with it.

Modelling this as a cost item would have meant either forcing a fake rate on
every wording line or making ``rate`` nullable in the upstream core — the first
corrupts the estimate, the second is a core change we would carry forever. A
table of our own costs nothing and survives every upstream merge.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base


class TextCatalog(Base):
    """A catalogue of position texts, e.g. "CAN 135 — Béton et béton armé"."""

    __tablename__ = "oe_neoffice_text_catalog"

    code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Reference standard the numbering follows: "CAN", "NPK", "free"…
    standard: Mapped[str] = mapped_column(String(20), nullable=False, default="CAN")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    #: Null = shared across the instance; set = private to one project.
    project_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    positions: Mapped[list["TextPosition"]] = relationship(
        back_populates="catalog",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TextPosition(Base):
    """One position text, or one sub-position under it.

    The same table holds both levels: a sub-position is simply a row whose
    ``parent_id`` points at its parent. That keeps ".01 / .02 / .03" a real
    hierarchy (orderable, indentable, extensible to a third level) instead of a
    naming convention nobody can query.
    """

    __tablename__ = "oe_neoffice_text_position"

    catalog_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("oe_neoffice_text_catalog.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("oe_neoffice_text_position.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    #: Full code as the estimator writes it: "135.046" or "135.046.01".
    code: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    #: Short label — the first line of the wording.
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    #: The rest of the wording, newlines preserved (a CAN text is multi-line).
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: NULL / empty on a wording line, set on a measurable sub-position.
    #: This is the whole point of the table: a text with no unit is not a
    #: priced article, and nothing downstream should treat it as one.
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Optional priced recipe. Picking this text in a BOQ brings the assembly.
    assembly_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    catalog: Mapped[TextCatalog] = relationship(back_populates="positions")
    children: Mapped[list["TextPosition"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TextPosition.sort_order",
    )
    parent: Mapped["TextPosition | None"] = relationship(
        back_populates="children", remote_side="TextPosition.id",
    )

    @property
    def is_measurable(self) -> bool:
        """A row that can carry a quantity in a BOQ (i.e. it has a unit)."""
        return bool(self.unit and self.unit.strip())
