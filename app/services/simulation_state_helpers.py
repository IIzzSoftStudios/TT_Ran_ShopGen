"""Helpers for ``SimulationState``: domain identity is always ``gm_profile_id``, never ``state_id``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models import SimulationState


def get_simulation_state_for_gm(session: Session, gm_id: int) -> Optional["SimulationState"]:
    """Load simulation state by GM profile id (the only domain lookup key)."""
    from app.models import SimulationState

    return session.query(SimulationState).filter_by(gm_profile_id=gm_id).first()
