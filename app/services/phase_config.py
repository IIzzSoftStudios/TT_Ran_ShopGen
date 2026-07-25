"""Load phase entitlements YAML once per worker (Flask app.extensions['phase_config'])."""
from __future__ import annotations

import os
from typing import Any, Dict, List

import yaml


class PhaseEntitlements:
    """Frozen in-memory phase dict for the lifetime of the worker process."""

    def __init__(self, file_path: str):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                raw = (content or {}).get("phases", {}) or {}
                self._phases: Dict[str, Dict[str, Any]] = {}
                for slug, row in raw.items():
                    if not isinstance(row, dict):
                        continue
                    self._phases[str(slug)] = dict(row)
        except Exception as e:
            raise RuntimeError(f"Failed to load phase entitlements: {e}") from e
        if "default" not in self._phases:
            raise KeyError("YAML must contain a 'default' phase slug.")
        self._validate_rows()

    def _validate_rows(self) -> None:
        for slug, row in self._phases.items():
            for key in ("label", "prefix", "campaign_limit", "seat_limit"):
                if key not in row:
                    raise KeyError(f"Phase '{slug}' missing required key '{key}'")
            # seat_limit may be null (unlimited); campaign_limit must be an int.
            if row.get("campaign_limit") is None:
                raise KeyError(f"Phase '{slug}' campaign_limit cannot be null")

    def get_phase(self, slug: str | None) -> Dict[str, Any]:
        """Return phase row or default if slug is missing, empty, or unknown."""
        if not slug:
            return dict(self._phases["default"])
        return dict(self._phases.get(str(slug), self._phases["default"]))

    def list_phases(self, include_internal: bool = False) -> List[str]:
        if include_internal:
            return list(self._phases.keys())
        return [s for s in self._phases if s not in ("test", "default")]


def resolve_phase_entitlements_path() -> str:
    """Path to phase_entitlements.yaml under TT_Ran_ShopGen/config/."""
    here = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(here)
    root = os.path.dirname(app_dir)
    return os.path.join(root, "config", "phase_entitlements.yaml")
