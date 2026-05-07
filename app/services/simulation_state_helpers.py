"""Helpers for ``SimulationState``: domain identity is always ``campaign_id``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models import SimulationState


def get_simulation_state_for_campaign(
    session: Session, campaign_id: int
) -> Optional["SimulationState"]:
    """Load simulation state by campaign id (the only domain lookup key)."""
    from app.models import SimulationState

    return session.query(SimulationState).filter_by(campaign_id=campaign_id).first()
