"""Runtime schema compatibility helpers.

Keeps the app operational when campaign scope columns have not yet been
applied via the full SQL migration script.
"""

from __future__ import annotations

import logging

from sqlalchemy import text, or_

from app.extensions import db

log = logging.getLogger(__name__)


_CAMPAIGN_SCOPE_TABLES = (
    "cities",
    "shops",
    "items",
    "shop_inventory",
    "regional_markets",
    "global_markets",
    "price_history",
    "demand_modifiers",
    "modifier_targets",
    "resource_transforms",
    "market_events",
    "simulation_logs",
    "sim_rules",
)


def ensure_campaign_scope_columns() -> bool:
    """Add missing campaign_id columns in-place for pre-migration DBs.

    Returns True when at least one table needed compatibility DDL.
    """
    patched_any = False
    for table_name in _CAMPAIGN_SCOPE_TABLES:
        table_exists = db.session.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": table_name},
        ).scalar_one_or_none()
        if table_exists is None:
            continue
        existing = db.session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table_name AND column_name = 'campaign_id'"
            ),
            {"table_name": table_name},
        ).first()
        if existing is None:
            patched_any = True
        sql = text(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS campaign_id INTEGER"
        )
        db.session.execute(sql)
    db.session.commit()
    return patched_any


def warn_if_compat_mode_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "campaign_scope_compat_mode enabled: runtime-added campaign_id columns. "
            "Run sql/campaign_scope_migration.sql to add constraints/indexes/backfill."
        )


def _regclass_exists(table_name: str) -> bool:
    return (
        db.session.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": table_name},
        ).scalar_one_or_none()
        is not None
    )


def _column_exists(table_name: str, column_name: str) -> bool:
    return (
        db.session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": table_name, "c": column_name},
        ).first()
        is not None
    )


def ensure_phase_entitlement_columns() -> bool:
    """Add key_phase / contact_name when missing (pre-migration dev DBs).

    Returns True if any DDL was applied. Prefer sql/phase_keys_and_contact_name.sql in prod.
    """
    patched_any = False
    if _regclass_exists("registration_key") and not _column_exists("registration_key", "key_phase"):
        patched_any = True
        db.session.execute(text("ALTER TABLE registration_key ADD COLUMN key_phase VARCHAR(40)"))
        db.session.execute(
            text("UPDATE registration_key SET key_phase = 'test' WHERE is_admin_test_key = true")
        )
        db.session.execute(
            text(
                "UPDATE registration_key SET key_phase = 'forge_master' "
                "WHERE COALESCE(is_admin_test_key, false) = false"
            )
        )
        db.session.execute(
            text("UPDATE registration_key SET key_phase = 'default' WHERE key_phase IS NULL")
        )
        db.session.execute(text("ALTER TABLE registration_key ALTER COLUMN key_phase SET NOT NULL"))
        db.session.execute(
            text("ALTER TABLE registration_key ALTER COLUMN key_phase SET DEFAULT 'default'")
        )

    if _regclass_exists("access_requests") and not _column_exists("access_requests", "contact_name"):
        patched_any = True
        db.session.execute(text("ALTER TABLE access_requests ADD COLUMN contact_name VARCHAR(120)"))
        db.session.execute(
            text(
                "UPDATE access_requests SET contact_name = 'Unknown' "
                "WHERE contact_name IS NULL OR trim(contact_name) = ''"
            )
        )
        db.session.execute(text("ALTER TABLE access_requests ALTER COLUMN contact_name SET NOT NULL"))
        db.session.execute(
            text("ALTER TABLE access_requests ALTER COLUMN contact_name SET DEFAULT ''")
        )

    if patched_any:
        db.session.commit()
    return patched_any


def warn_if_phase_compat_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "phase_key_compat_mode enabled: runtime-added key_phase / contact_name. "
            "Run sql/phase_keys_and_contact_name.sql for controlled migrations."
        )


def ensure_user_password_history_table() -> bool:
    """Create user_password_history if missing (password reuse policy).

    Returns True when the table was created by this bootstrap.
    """
    if _regclass_exists("user_password_history"):
        return False
    if not _regclass_exists("user"):
        return False
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_password_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                password_hash VARCHAR(128) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
            )
            """
        )
    )
    db.session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_uph_user_id ON user_password_history (user_id)")
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_uph_user_created "
            "ON user_password_history (user_id, created_at)"
        )
    )
    db.session.commit()
    return True


def warn_if_password_history_compat_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "user_password_history table created via compat bootstrap. "
            "Add a formal migration in production if you manage schema via Alembic."
        )


def ensure_player_npc_columns() -> bool:
    """Add is_npc and allow NULL on player user FK columns for GM-only NPC rows.

    Handles both legacy `user_id_player` and drifted `user_id_gm` column names.

    Returns True if any DDL was applied.
    """
    patched_any = False
    if not _regclass_exists("player"):
        return False

    if not _column_exists("player", "is_npc"):
        patched_any = True
        db.session.execute(
            text("ALTER TABLE player ADD COLUMN is_npc BOOLEAN NOT NULL DEFAULT false")
        )

    for col in ("user_id_gm", "user_id_player"):
        if not _column_exists("player", col):
            continue
        null_sql = text(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'player' AND column_name = :c
            """
        )
        row = db.session.execute(null_sql, {"c": col}).first()
        if row and (row[0] or "").upper() == "NO":
            patched_any = True
            db.session.execute(text(f"ALTER TABLE player ALTER COLUMN {col} DROP NOT NULL"))

    needs_commit = patched_any
    if _column_exists("player", "user_id_gm") and _column_exists(
        "player", "user_id_player"
    ):
        res = db.session.execute(
            text(
                "UPDATE player SET user_id_gm = user_id_player "
                "WHERE user_id_gm IS NULL AND user_id_player IS NOT NULL"
            )
        )
        rc = getattr(res, "rowcount", None)
        if rc is not None and rc > 0:
            needs_commit = True

    if needs_commit:
        db.session.commit()
    return patched_any


def warn_if_player_npc_compat_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "player NPC compat bootstrap applied (is_npc, nullable user FK columns). "
            "Run sql/player_npc_migration.sql in production if you manage schema manually."
        )


def ensure_join_codes_columns() -> bool:
    """Add campaign/player join_code columns, backfill, and (user, gm) uniqueness on player.

    PostgreSQL-oriented (matches other helpers in this module).
    """
    patched_any = False
    if not _regclass_exists("campaign") or not _regclass_exists("player"):
        return False

    if not _column_exists("campaign", "join_code"):
        patched_any = True
        db.session.execute(text("ALTER TABLE campaign ADD COLUMN join_code VARCHAR(32)"))
        db.session.commit()

    if not _column_exists("player", "join_code"):
        patched_any = True
        db.session.execute(text("ALTER TABLE player ADD COLUMN join_code VARCHAR(32)"))
        db.session.commit()

    for conname in ("player_user_id_gm_key", "player_user_id_player_key"):
        db.session.execute(text(f"ALTER TABLE player DROP CONSTRAINT IF EXISTS {conname}"))
        patched_any = True
    db.session.commit()

    # (user_id_gm, gm_profile_id) uniqueness + solo row: partial indexes in
    # ensure_solo_player_vault_schema (PostgreSQL). Do not re-add uq_player_user_gm here.

    from app.models import Campaign, Player
    from app.services.join_codes import CAMPAIGN_PREFIX, PLAYER_PREFIX, generate_raw_code

    for camp in Campaign.query.filter(
        or_(Campaign.join_code.is_(None), Campaign.join_code == "")
    ).all():
        patched_any = True
        for _ in range(20):
            code = generate_raw_code(CAMPAIGN_PREFIX)
            if not Campaign.query.filter(Campaign.join_code == code).first():
                camp.join_code = code
                break
        db.session.commit()

    for pl in (
        Player.query.filter(Player.is_npc.is_(False))
        .filter(or_(Player.join_code.is_(None), Player.join_code == ""))
        .all()
    ):
        patched_any = True
        for _ in range(20):
            code = generate_raw_code(PLAYER_PREFIX)
            if not Player.query.filter(Player.join_code == code).first():
                pl.join_code = code
                break
        db.session.commit()

    return patched_any


def warn_if_join_codes_compat_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "join_codes compat bootstrap applied (join_code columns, uq_player_user_gm). "
            "Prefer a formal migration in production."
        )


def ensure_solo_player_vault_schema() -> bool:
    """Solo Player (nullable gm_profile_id) + vault character sheets (nullable campaign_id).

    PostgreSQL only (partial unique indexes). Drops legacy ``uq_player_user_gm`` and
    ``uq_sheet_player_campaign`` in favor of partial uniques.

    Returns True when any DDL ran.
    """
    if db.engine.dialect.name != "postgresql":
        return False

    patched_any = False

    if _regclass_exists("player"):
        if (
            db.session.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = 'uq_player_user_gm'")
            ).first()
            is not None
        ):
            patched_any = True
        db.session.execute(
            text("ALTER TABLE player DROP CONSTRAINT IF EXISTS uq_player_user_gm")
        )
        gm_null = db.session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'player' "
                "AND column_name = 'gm_profile_id'"
            )
        ).first()
        if gm_null and (gm_null[0] or "").upper() == "NO":
            patched_any = True
            db.session.execute(
                text("ALTER TABLE player ALTER COLUMN gm_profile_id DROP NOT NULL")
            )
        db.session.commit()

        for idx_name, idx_sql in (
            (
                "uq_player_solo_vault",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_player_solo_vault
                ON player (user_id_gm)
                WHERE gm_profile_id IS NULL AND is_npc = false AND user_id_gm IS NOT NULL
                """,
            ),
            (
                "uq_player_user_gm_nonempty",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_player_user_gm_nonempty
                ON player (user_id_gm, gm_profile_id)
                WHERE gm_profile_id IS NOT NULL AND is_npc = false AND user_id_gm IS NOT NULL
                """,
            ),
        ):
            exists = db.session.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"
                ),
                {"n": idx_name},
            ).first()
            if exists is None:
                patched_any = True
                db.session.execute(text(idx_sql))
        db.session.commit()

    if _regclass_exists("player_character_sheet"):
        if (
            db.session.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = 'uq_sheet_player_campaign'"
                )
            ).first()
            is not None
        ):
            patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE player_character_sheet DROP CONSTRAINT IF EXISTS uq_sheet_player_campaign"
            )
        )
        cid_null = db.session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'player_character_sheet' "
                "AND column_name = 'campaign_id'"
            )
        ).first()
        if cid_null and (cid_null[0] or "").upper() == "NO":
            patched_any = True
            db.session.execute(
                text(
                    "ALTER TABLE player_character_sheet ALTER COLUMN campaign_id DROP NOT NULL"
                )
            )
        db.session.commit()

        for idx_name, idx_sql in (
            (
                "uq_sheet_player_campaign_nn",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sheet_player_campaign_nn
                ON player_character_sheet (player_id, campaign_id)
                WHERE campaign_id IS NOT NULL
                """,
            ),
            (
                "uq_sheet_player_vault",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sheet_player_vault
                ON player_character_sheet (player_id)
                WHERE campaign_id IS NULL
                """,
            ),
        ):
            exists = db.session.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"
                ),
                {"n": idx_name},
            ).first()
            if exists is None:
                patched_any = True
                db.session.execute(text(idx_sql))
        db.session.commit()

    return patched_any


def warn_if_solo_vault_compat_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "solo_player_vault compat bootstrap applied (nullable gm_profile_id / "
            "campaign_id, partial unique indexes). Prefer a formal migration in production."
        )


def ensure_simulation_state_click_columns() -> bool:
    """Add ``sim_clicks_*`` counters on ``simulation_state`` when missing (pre-TTRSG refresh DBs).

    Returns True if any column was added.
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("simulation_state"):
        return False

    patched_any = False
    for col in (
        "sim_clicks_day",
        "sim_clicks_week",
        "sim_clicks_month",
        "sim_clicks_year",
        "sim_clicks_pause",
    ):
        if _column_exists("simulation_state", col):
            continue
        patched_any = True
        db.session.execute(
            text(
                f"ALTER TABLE simulation_state ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
            )
        )
    if patched_any:
        db.session.commit()
    return patched_any


def warn_if_simulation_state_clicks_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "simulation_state sim_clicks_* columns were added by schema compat. "
            "Align with TTRSG_TableCreation.sql in production."
        )
