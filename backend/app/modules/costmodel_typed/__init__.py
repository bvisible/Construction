"""Typed cost components & yield library — generic extension of the Cost Spine.

This module adds a typed component layer (labor / machine / material / internal
loc / external margin / subcontractor margin / misc / transport / fg_admin)
hanging off ``oe_costmodel_cost_line``, plus a project-scoped (or global)
yield library tracking productivity rates (U/h) for each task. It is the
generic substrate that downstream / private modules subscribe to in order to
inject domain-specific pricing rules through the EventBus.

Tables
~~~~~~

* ``oe_assembly_component`` — typed sub-block component attached to a CostLine
* ``oe_yield_library`` — productivity rates (U/h) library, project-scoped or global

Events
~~~~~~

* ``costmodel_typed.component.created`` — published after a component is created
* ``costmodel_typed.component.updated`` — published after a component is updated
* ``costmodel_typed.component.deleted`` — published after a component is deleted
* ``costmodel_typed.cost_line.recomputed`` — published after a CostLine total has been recomputed
* ``costmodel_typed.yield_library.entry_created`` — published after a yield entry is created
"""
