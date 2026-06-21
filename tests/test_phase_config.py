import pytest
import yaml

from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path


def test_phase_entitlements_loads_repo_yaml():
    path = resolve_phase_entitlements_path()
    assert path.endswith("phase_entitlements.yaml")
    pe = PhaseEntitlements(path)
    assert "default" in pe.list_phases(include_internal=True)
    d = pe.get_phase(None)
    assert d["campaign_limit"] >= 1
    assert d["seat_limit"] >= 1


def test_get_phase_unknown_returns_default(phase_yaml_path):
    pe = PhaseEntitlements(phase_yaml_path)
    row = pe.get_phase("missing_slug_xyz")
    assert row["label"] == "Def"
    assert row["campaign_limit"] == 1


def test_list_phases_filters_internal(phase_yaml_path):
    pe = PhaseEntitlements(phase_yaml_path)
    pub = pe.list_phases(include_internal=False)
    assert "test" not in pub
    assert "default" not in pub
    assert "alpha" in pub
    all_slugs = pe.list_phases(include_internal=True)
    assert set(all_slugs) >= {"default", "alpha", "test"}


def test_missing_default_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump({"phases": {"alpha": {"label": "a", "prefix": "A", "campaign_limit": 1, "seat_limit": 1}}}), encoding="utf-8")
    with pytest.raises(KeyError):
        PhaseEntitlements(str(bad))
