"""Per-encounter tactical battle map: uploads, procedural terrain, grid resize.

Presentation/combat state only — never imported by the economy simulation tick.
Storage is abstracted so tests can inject a fake backend without disk or cloud I/O.
"""

from __future__ import annotations

import io
import logging
import math
import os
import random
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image

from app.extensions import db
from app.models import BattleCombatant, BattleEncounter
from app.services.combat import CombatValidationError
from app.services.combat.encounter_service import MAX_GRID, MIN_GRID, validate_grid_dimensions

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_MAP_EDGE = 2048
MAX_IMAGE_PIXELS = 32_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

TERRAIN_PRESETS = frozenset(
    {
        "plains",
        "forest",
        "mountains",
        "river",
        "village",
        "road",
        "encampment",
        "small_fort",
    }
)

MAP_SOURCE_NONE = "none"
MAP_SOURCE_GENERATED = "generated"
MAP_SOURCE_UPLOADED = "uploaded"
MAP_SOURCES = frozenset({MAP_SOURCE_NONE, MAP_SOURCE_GENERATED, MAP_SOURCE_UPLOADED})

GENERATION_SCHEMA_VERSION = 1
MAX_FEATURES_PER_CELL = 0.35
CHUNK_THRESHOLD = 150
CHUNK_CELL_SIZE = 64
MAX_CHUNK_WINDOW = 96


class BattleMapValidationError(ValueError):
    """Raised when battle map input fails validation."""


class BattleMapStorage:
    """Abstract storage for uploaded battle map WebP bytes."""

    def write(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def read(self, key: str) -> bytes | None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def list_keys(self) -> list[str]:
        raise NotImplementedError


class LocalBattleMapStorage(BattleMapStorage):
    """Development/single-instance filesystem storage."""

    def __init__(self, root: Path | None = None):
        if root is None:
            app_root = Path(current_app.root_path).parent
            root = app_root / "uploads" / "battle_maps"
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = Path(key).name
        if safe != key or ".." in key:
            raise BattleMapValidationError("Invalid asset key.")
        return self.root / safe

    def write(self, key: str, data: bytes) -> None:
        self._path(key).write_bytes(data)

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        if not path.exists():
            return None
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            log.warning("battle_map_delete_deferred key=%s", key)

    def list_keys(self) -> list[str]:
        return [p.name for p in self.root.glob("*.webp")]


class MemoryBattleMapStorage(BattleMapStorage):
    """In-memory storage for tests."""

    def __init__(self):
        self._blobs: dict[str, bytes] = {}

    def write(self, key: str, data: bytes) -> None:
        self._blobs[key] = data

    def read(self, key: str) -> bytes | None:
        return self._blobs.get(key)

    def delete(self, key: str) -> None:
        self._blobs.pop(key, None)

    def list_keys(self) -> list[str]:
        return list(self._blobs.keys())


_storage_override: BattleMapStorage | None = None


def get_storage() -> BattleMapStorage:
    if _storage_override is not None:
        return _storage_override
    return LocalBattleMapStorage()


def set_storage(storage: BattleMapStorage | None) -> None:
    global _storage_override
    _storage_override = storage


def _round_norm(x: float, y: float) -> list[float]:
    return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]


def _blob(rng: random.Random, cx: float, cy: float, rx: float, ry: float, n: int):
    pts = []
    for i in range(n):
        angle = (math.tau * i / n) + rng.uniform(-0.2, 0.2)
        wobble = rng.uniform(0.7, 1.2)
        pts.append(
            _round_norm(cx + math.cos(angle) * rx * wobble, cy + math.sin(angle) * ry * wobble)
        )
    return pts


def _polyline(rng: random.Random, start, end, bends: int, jitter: float):
    pts = []
    for i in range(bends + 2):
        t = i / (bends + 1)
        x = start[0] + (end[0] - start[0]) * t + rng.uniform(-jitter, jitter)
        y = start[1] + (end[1] - start[1]) * t + rng.uniform(-jitter, jitter)
        pts.append(_round_norm(x, y))
    return pts


def _feature_cap(grid_width: int, grid_height: int) -> int:
    area = max(1, grid_width * grid_height)
    return max(8, min(120, int(area * MAX_FEATURES_PER_CELL)))


def _palette_for_preset(preset: str) -> dict:
    palettes = {
        "plains": {"base": "#8fbc8f", "accent": "#6b8e4e", "detail": "#c4a35a"},
        "forest": {"base": "#3d5c3a", "accent": "#2a4028", "detail": "#5a7a48"},
        "mountains": {"base": "#7a8491", "accent": "#4a5568", "detail": "#a0aec0"},
        "river": {"base": "#7ec8e3", "accent": "#4a90a4", "detail": "#8fbc8f"},
        "village": {"base": "#c9b896", "accent": "#8b7355", "detail": "#6b5344"},
        "road": {"base": "#b8a88a", "accent": "#8a7a62", "detail": "#9a8b72"},
        "encampment": {"base": "#a09078", "accent": "#6b5d4f", "detail": "#c4b498"},
        "small_fort": {"base": "#8a8a8a", "accent": "#555555", "detail": "#b0b0b0"},
    }
    return palettes.get(preset, palettes["plains"])


def generate_terrain_metadata(
    preset: str,
    seed: int,
    grid_width: int,
    grid_height: int,
) -> dict:
    """Deterministic procedural battle-map feature list (visual only)."""
    preset = _validate_preset(preset)
    rng = random.Random(seed)
    cap = _feature_cap(grid_width, grid_height)
    features: list[dict] = []

    def add(feature: dict) -> None:
        if len(features) < cap:
            features.append(feature)

    if preset == "plains":
        for _ in range(min(6, cap // 3)):
            add(
                {
                    "type": "patch",
                    "kind": "grass",
                    "points": _blob(
                        rng,
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.08, 0.18),
                        rng.uniform(0.08, 0.18),
                        rng.randint(5, 8),
                    ),
                }
            )
    elif preset == "forest":
        for _ in range(min(12, cap // 2)):
            add(
                {
                    "type": "patch",
                    "kind": "trees",
                    "points": _blob(
                        rng,
                        rng.uniform(0.05, 0.95),
                        rng.uniform(0.05, 0.95),
                        rng.uniform(0.04, 0.1),
                        rng.uniform(0.04, 0.1),
                        rng.randint(6, 9),
                    ),
                }
            )
    elif preset == "mountains":
        for _ in range(min(8, cap // 2)):
            add(
                {
                    "type": "patch",
                    "kind": "rock",
                    "points": _blob(
                        rng,
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.06, 0.14),
                        rng.uniform(0.05, 0.12),
                        rng.randint(5, 7),
                    ),
                }
            )
    elif preset == "river":
        add(
            {
                "type": "river",
                "kind": "water",
                "points": _polyline(
                    rng,
                    (0.05, rng.uniform(0.2, 0.8)),
                    (0.95, rng.uniform(0.2, 0.8)),
                    rng.randint(4, 7),
                    0.06,
                ),
            }
        )
        for _ in range(min(5, cap // 4)):
            add(
                {
                    "type": "patch",
                    "kind": "grass",
                    "points": _blob(
                        rng,
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.1, 0.9),
                        rng.uniform(0.06, 0.12),
                        rng.uniform(0.06, 0.12),
                        6,
                    ),
                }
            )
    elif preset == "village":
        for _ in range(min(5, cap // 3)):
            add(
                {
                    "type": "building",
                    "kind": "house",
                    "x": round(rng.uniform(0.15, 0.85), 4),
                    "y": round(rng.uniform(0.15, 0.85), 4),
                    "w": round(rng.uniform(0.06, 0.12), 4),
                    "h": round(rng.uniform(0.06, 0.12), 4),
                }
            )
        add(
            {
                "type": "road",
                "kind": "path",
                "points": _polyline(rng, (0.1, 0.5), (0.9, 0.5), 2, 0.02),
            }
        )
    elif preset == "road":
        add(
            {
                "type": "road",
                "kind": "path",
                "points": _polyline(
                    rng,
                    (0.05, rng.uniform(0.3, 0.7)),
                    (0.95, rng.uniform(0.3, 0.7)),
                    rng.randint(2, 4),
                    0.025,
                ),
            }
        )
    elif preset == "encampment":
        for _ in range(min(6, cap // 3)):
            add(
                {
                    "type": "tent",
                    "kind": "camp",
                    "x": round(rng.uniform(0.1, 0.9), 4),
                    "y": round(rng.uniform(0.1, 0.9), 4),
                    "size": round(rng.uniform(0.04, 0.08), 4),
                }
            )
        add(
            {
                "type": "patch",
                "kind": "dirt",
                "points": _blob(rng, 0.5, 0.5, 0.35, 0.35, 8),
            }
        )
    elif preset == "small_fort":
        add(
            {
                "type": "wall",
                "kind": "fort",
                "points": _blob(rng, 0.5, 0.5, 0.32, 0.32, 10),
            }
        )
        add(
            {
                "type": "building",
                "kind": "keep",
                "x": 0.42,
                "y": 0.42,
                "w": 0.16,
                "h": 0.16,
            }
        )

    return {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "preset": preset,
        "seed": seed,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "palette": _palette_for_preset(preset),
        "features": features,
    }


def _validate_preset(preset) -> str:
    if preset is None:
        return "plains"
    cleaned = str(preset).strip().lower()
    if cleaned not in TERRAIN_PRESETS:
        raise BattleMapValidationError(
            f"terrain_preset must be one of: {', '.join(sorted(TERRAIN_PRESETS))}."
        )
    return cleaned


def _validate_source(source) -> str:
    cleaned = str(source or MAP_SOURCE_NONE).strip().lower()
    if cleaned not in MAP_SOURCES:
        raise BattleMapValidationError("Invalid map_source_type.")
    return cleaned


def _new_asset_key(encounter_id: int) -> str:
    return f"encounter_{encounter_id}_{uuid.uuid4().hex}.webp"


def _bump_map_version(encounter: BattleEncounter) -> None:
    encounter.map_version = int(encounter.map_version or 0) + 1


def delete_asset_key(key: str | None) -> None:
    """Best-effort delete of a storage key (typically after DB commit)."""
    if not key:
        return
    get_storage().delete(key)


def map_stub(encounter: BattleEncounter) -> dict:
    return {
        "source_type": _validate_source(encounter.map_source_type),
        "terrain_preset": encounter.terrain_preset,
        "terrain_seed": encounter.terrain_seed,
        "has_image": bool(encounter.map_asset_key),
        "map_version": int(encounter.map_version or 0),
    }


def is_chunked_map(encounter: BattleEncounter) -> bool:
    """Large generated maps expose terrain through chunk requests only."""
    if encounter.map_source_type != MAP_SOURCE_GENERATED:
        return False
    return (
        encounter.grid_width > CHUNK_THRESHOLD
        or encounter.grid_height > CHUNK_THRESHOLD
    )


def _feature_intersects_region(
    feat: dict, nx0: float, ny0: float, nx1: float, ny1: float
) -> bool:
    t = feat.get("type")
    if t in {"patch", "wall", "river", "road"}:
        for point in feat.get("points") or []:
            if len(point) < 2:
                continue
            if nx0 <= point[0] < nx1 and ny0 <= point[1] < ny1:
                return True
        return False
    if t in {"building", "tent"}:
        x = float(feat.get("x", 0))
        y = float(feat.get("y", 0))
        return nx0 <= x < nx1 and ny0 <= y < ny1
    return False


def _terrain_metadata_for_encounter(encounter: BattleEncounter) -> dict:
    if encounter.terrain_metadata:
        return encounter.terrain_metadata
    if encounter.map_source_type != MAP_SOURCE_GENERATED:
        return {}
    preset = encounter.terrain_preset or "plains"
    seed = int(encounter.terrain_seed or 0)
    return generate_terrain_metadata(
        preset, seed, encounter.grid_width, encounter.grid_height
    )


def terrain_chunk_payload(
    encounter: BattleEncounter, chunk_x: int, chunk_y: int
) -> dict:
    """Return terrain features for a fixed chunk window."""
    try:
        chunk_x = int(chunk_x)
        chunk_y = int(chunk_y)
    except (TypeError, ValueError) as exc:
        raise BattleMapValidationError("Chunk coordinates must be integers.") from exc
    if chunk_x < 0 or chunk_y < 0:
        raise BattleMapValidationError("Chunk coordinates must be non-negative.")
    max_chunk_x = max(
        0, math.ceil(encounter.grid_width / CHUNK_CELL_SIZE) - 1
    )
    max_chunk_y = max(
        0, math.ceil(encounter.grid_height / CHUNK_CELL_SIZE) - 1
    )
    if chunk_x > max_chunk_x or chunk_y > max_chunk_y:
        raise BattleMapValidationError("Chunk coordinates out of range.")

    x0 = chunk_x * CHUNK_CELL_SIZE
    y0 = chunk_y * CHUNK_CELL_SIZE
    x1 = min(encounter.grid_width, x0 + CHUNK_CELL_SIZE)
    y1 = min(encounter.grid_height, y0 + CHUNK_CELL_SIZE)
    gw = max(1, encounter.grid_width)
    gh = max(1, encounter.grid_height)
    nx0, ny0 = x0 / gw, y0 / gh
    nx1, ny1 = x1 / gw, y1 / gh

    meta = _terrain_metadata_for_encounter(encounter)
    features = [
        feat
        for feat in meta.get("features") or []
        if _feature_intersects_region(feat, nx0, ny0, nx1, ny1)
    ]
    return {
        "chunk_x": chunk_x,
        "chunk_y": chunk_y,
        "chunk_size": CHUNK_CELL_SIZE,
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "map_version": int(encounter.map_version or 0),
        "terrain_metadata": {
            "schema_version": meta.get("schema_version", GENERATION_SCHEMA_VERSION),
            "preset": meta.get("preset", encounter.terrain_preset),
            "seed": meta.get("seed", encounter.terrain_seed),
            "grid_width": encounter.grid_width,
            "grid_height": encounter.grid_height,
            "palette": meta.get("palette") or _palette_for_preset(
                encounter.terrain_preset or "plains"
            ),
            "features": features,
        },
    }


def map_payload(encounter: BattleEncounter) -> dict:
    stub = map_stub(encounter)
    payload = {
        **stub,
        "grid_width": encounter.grid_width,
        "grid_height": encounter.grid_height,
        "chunked": is_chunked_map(encounter),
        "chunk_size": CHUNK_CELL_SIZE,
        "chunk_threshold": CHUNK_THRESHOLD,
    }
    if is_chunked_map(encounter):
        payload["terrain_metadata"] = {}
        payload["chunk_cols"] = math.ceil(encounter.grid_width / CHUNK_CELL_SIZE)
        payload["chunk_rows"] = math.ceil(encounter.grid_height / CHUNK_CELL_SIZE)
    else:
        payload["terrain_metadata"] = encounter.terrain_metadata or {}
    if encounter.map_asset_key:
        payload["image_url"] = f"/api/combat/encounters/{encounter.id}/map/image"
    else:
        payload["image_url"] = None
    return payload


def read_upload_bytes(encounter: BattleEncounter) -> bytes | None:
    if not encounter.map_asset_key:
        return None
    return get_storage().read(encounter.map_asset_key)


def _require_setup(encounter: BattleEncounter) -> None:
    if encounter.status != "setup":
        raise CombatValidationError(
            "Map and grid changes are only allowed during encounter setup."
        )


def initialize_generated_map(
    encounter: BattleEncounter,
    preset: str | None = None,
    seed: int | None = None,
) -> str | None:
    """Apply a new procedural map to a setup encounter.

    Returns the previous uploaded asset key to delete after a successful commit.
    """
    _require_setup(encounter)
    preset = _validate_preset(preset or encounter.terrain_preset or "plains")
    if seed is None:
        seed = random.SystemRandom().randint(0, 0x7FFFFFFF)
    old_key = encounter.map_asset_key
    encounter.terrain_preset = preset
    encounter.terrain_seed = int(seed)
    encounter.terrain_metadata = generate_terrain_metadata(
        preset, int(seed), encounter.grid_width, encounter.grid_height
    )
    encounter.map_source_type = MAP_SOURCE_GENERATED
    encounter.map_asset_key = None
    _bump_map_version(encounter)
    db.session.flush()
    return old_key


def regenerate_map(encounter: BattleEncounter, preset: str | None = None) -> str | None:
    """Regenerate procedural terrain (new seed)."""
    new_preset = _validate_preset(preset or encounter.terrain_preset or "plains")
    seed = random.SystemRandom().randint(0, 0x7FFFFFFF)
    return initialize_generated_map(encounter, preset=new_preset, seed=seed)


def save_upload(encounter: BattleEncounter, file_storage) -> tuple[str | None, str | None]:
    """Validate, convert, and store an uploaded battle map image.

    Returns ``(previous_key, new_key)`` so callers can delete the previous asset
    only after commit succeeds and roll back the new asset if commit fails.
    """
    _require_setup(encounter)
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    if size > MAX_UPLOAD_BYTES:
        raise BattleMapValidationError("File exceeds max 4 MB allowed size.")
    file_storage.stream.seek(0)

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        img = Image.open(file_storage.stream)
        img_format = img.format
    except Exception as exc:
        raise BattleMapValidationError("File is not a readable image.") from exc
    if img_format not in ALLOWED_FORMATS:
        raise BattleMapValidationError(
            "Unsupported image format. Use PNG, JPEG, WebP, or GIF."
        )
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise BattleMapValidationError("Image exceeds maximum pixel count.")

    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail((MAX_MAP_EDGE, MAX_MAP_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)
    data = out.getvalue()

    new_key = _new_asset_key(encounter.id)
    storage = get_storage()
    old_key = encounter.map_asset_key
    try:
        storage.write(new_key, data)
    except Exception as exc:
        raise BattleMapValidationError("Could not save battle map upload.") from exc

    encounter.map_asset_key = new_key
    encounter.map_source_type = MAP_SOURCE_UPLOADED
    encounter.terrain_metadata = None
    encounter.terrain_preset = None
    encounter.terrain_seed = None
    _bump_map_version(encounter)
    db.session.flush()
    return old_key, new_key


def resize_grid(encounter: BattleEncounter, width, height) -> None:
    """Resize encounter grid during setup; rejects if tokens would clip."""
    _require_setup(encounter)
    width, height = validate_grid_dimensions(width, height)
    combatants = BattleCombatant.query.filter_by(encounter_id=encounter.id).all()
    max_x = max((c.x for c in combatants if c.status != "removed"), default=-1)
    max_y = max((c.y for c in combatants if c.status != "removed"), default=-1)
    if width <= max_x or height <= max_y:
        raise CombatValidationError(
            "Grid is too small for combatants already placed on the map."
        )
    encounter.grid_width = width
    encounter.grid_height = height
    if encounter.map_source_type == MAP_SOURCE_GENERATED and encounter.terrain_preset:
        seed = encounter.terrain_seed or 0
        encounter.terrain_metadata = generate_terrain_metadata(
            encounter.terrain_preset, seed, width, height
        )
        _bump_map_version(encounter)
    db.session.flush()


def cleanup_encounter_assets(encounter: BattleEncounter) -> None:
    """Best-effort delete uploaded assets when an encounter is removed."""
    if encounter.map_asset_key:
        delete_asset_key(encounter.map_asset_key)


def find_orphan_asset_keys() -> list[str]:
    """Return storage keys not referenced by any encounter row."""
    referenced = {
        row[0]
        for row in db.session.query(BattleEncounter.map_asset_key)
        .filter(BattleEncounter.map_asset_key.isnot(None))
        .all()
    }
    return [k for k in get_storage().list_keys() if k not in referenced]
