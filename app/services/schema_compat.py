"""Runtime schema compatibility helpers.

Keeps the app operational when campaign scope columns have not yet been
applied via the full SQL migration script.
"""

from __future__ import annotations

import json
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
    if not _regclass_exists("user") or not _regclass_exists("gm_profile"):
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


def ensure_user_avatar_column() -> bool:
    """Add account-menu avatar timestamp column when missing."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("user") or not _regclass_exists("gm_profile"):
        return False
    if _column_exists("user", "avatar_updated_at"):
        return False
    db.session.execute(
        text(
            'ALTER TABLE "user" ADD COLUMN avatar_updated_at '
            "TIMESTAMP WITHOUT TIME ZONE"
        )
    )
    db.session.commit()
    return True


def warn_if_user_avatar_column_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "user.avatar_updated_at added via compat bootstrap. "
            "Run sql/migrations/005_user_avatar.sql in controlled deploys."
        )


def ensure_user_submissions_table() -> bool:
    """Create user_submissions when missing (account menu feedback)."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("user"):
        return False
    if _regclass_exists("user_submissions"):
        return False
    db.session.execute(
        text(
            """
            CREATE TABLE user_submissions (
                id SERIAL PRIMARY KEY,
                kind VARCHAR(20) NOT NULL,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                username_snapshot VARCHAR(100) NOT NULL,
                submitted_session_mode VARCHAR(20) NOT NULL,
                account_role VARCHAR(50) NOT NULL,
                category VARCHAR(50) NOT NULL,
                title VARCHAR(120),
                body TEXT NOT NULL,
                extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                page_url VARCHAR(500) NOT NULL,
                campaign_id INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                    DEFAULT (NOW() AT TIME ZONE 'utc')
            )
            """
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_user_submissions_kind_status "
            "ON user_submissions(kind, status)"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_user_submissions_created_at "
            "ON user_submissions(created_at DESC)"
        )
    )
    db.session.commit()
    return True


def warn_if_user_submissions_table_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "user_submissions table created via compat bootstrap. "
            "Run sql/migrations/004_user_submissions.sql in controlled deploys."
        )


def ensure_expansion_interest_table() -> bool:
    """Create expansion_interest when missing (paid-tier demand telemetry)."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("user") or not _regclass_exists("gm_profile"):
        return False
    if _regclass_exists("expansion_interest"):
        return False
    db.session.execute(
        text(
            """
            CREATE TABLE expansion_interest (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                gm_profile_id INTEGER REFERENCES gm_profile(id) ON DELETE SET NULL,
                intent VARCHAR(64) NOT NULL DEFAULT 'campaign_limit_upgrade',
                source VARCHAR(80),
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                    DEFAULT (NOW() AT TIME ZONE 'utc')
            )
            """
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_expansion_interest_user_created "
            "ON expansion_interest(user_id, created_at DESC)"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_expansion_interest_gm_created "
            "ON expansion_interest(gm_profile_id, created_at DESC)"
        )
    )
    db.session.commit()
    return True


def warn_if_expansion_interest_table_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "expansion_interest table created via compat bootstrap. "
            "Run sql/expansion_interest_create.sql in controlled deploys."
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
    """Add campaign/player join_code columns and backfill missing codes.

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

    # Player uniqueness belongs to the character-vault compatibility helper.
    # Do not re-add legacy one-player-per-GM constraints here.

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
            "join_codes compat bootstrap applied (join_code columns/backfill). "
            "Prefer a formal migration in production."
        )


def ensure_solo_player_vault_schema() -> bool:
    """Solo Player (nullable gm_profile_id) + vault character sheets (nullable campaign_id).

    PostgreSQL only (partial unique indexes). Drops legacy ``uq_player_user_gm``,
    ``uq_player_user_gm_nonempty``, and ``uq_sheet_player_campaign`` in favor of
    per-character rows and sheet-level partial uniques.

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

        solo_idx = db.session.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_player_solo_vault'"
            )
        ).first()
        if solo_idx is not None:
            patched_any = True
            db.session.execute(text("DROP INDEX IF EXISTS uq_player_solo_vault"))

        user_gm_idx = db.session.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'uq_player_user_gm_nonempty'"
            )
        ).first()
        if user_gm_idx is not None:
            patched_any = True
            db.session.execute(text("DROP INDEX IF EXISTS uq_player_user_gm_nonempty"))
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


def _sqlite_table_exists(table_name: str) -> bool:
    return (
        db.session.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"
            ),
            {"n": table_name},
        ).first()
        is not None
    )


def _sqlite_column_exists(table_name: str, column_name: str) -> bool:
    if not _sqlite_table_exists(table_name):
        return False
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def ensure_global_market_baseline_stock_column() -> bool:
    """Add ``baseline_avg_stock`` on ``global_markets`` and ``last_market_run`` on ``simulation_state``.

    Runs a best-effort backfill of baseline stock from current inventory averages for
    rows where baseline is NULL or zero. Pre-existing worlds may have slightly stale baselines.
    """
    dialect = db.engine.dialect.name
    if dialect == "sqlite":
        patched_any = False
        if _sqlite_table_exists("simulation_state") and not _sqlite_column_exists(
            "simulation_state", "last_market_run"
        ):
            patched_any = True
            db.session.execute(
                text("ALTER TABLE simulation_state ADD COLUMN last_market_run JSON")
            )
        if patched_any:
            db.session.commit()
        return patched_any

    if dialect != "postgresql":
        return False

    patched_any = False

    if _regclass_exists("global_markets") and not _column_exists(
        "global_markets", "baseline_avg_stock"
    ):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE global_markets "
                "ADD COLUMN baseline_avg_stock DOUBLE PRECISION"
            )
        )

    if _regclass_exists("simulation_state") and not _column_exists(
        "simulation_state", "last_market_run"
    ):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE simulation_state ADD COLUMN last_market_run JSONB"
            )
        )

    if patched_any:
        db.session.commit()

    if _regclass_exists("global_markets") and _column_exists(
        "global_markets", "baseline_avg_stock"
    ):
        try:
            db.session.execute(
                text(
                    """
                    UPDATE global_markets gm
                    SET baseline_avg_stock = sub.avg_stock
                    FROM (
                        SELECT s.campaign_id, si.item_id,
                               COALESCE(AVG(si.stock), 0.0) AS avg_stock
                        FROM shop_inventory si
                        JOIN shops s ON si.shop_id = s.shop_id
                        GROUP BY s.campaign_id, si.item_id
                    ) sub
                    WHERE gm.campaign_id = sub.campaign_id
                      AND gm.item_id = sub.item_id
                      AND (gm.baseline_avg_stock IS NULL OR gm.baseline_avg_stock = 0.0)
                    """
                )
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            log.error("Failed to backfill baseline_avg_stock on global_markets: %s", exc)

    return patched_any


def warn_if_global_market_baseline_stock_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "global_markets.baseline_avg_stock and/or simulation_state.last_market_run "
            "were added by schema compat. Align with TTRSG_TableCreation.sql in production."
        )


# ---------------------------------------------------------------------------
# Campaign re-key migration: drop gm_profile_id from world + simulation tables.
# ---------------------------------------------------------------------------

# Tables that get a NOT NULL campaign_id and lose gm_profile_id.
_CAMPAIGN_REKEY_TABLES = (
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


def _gm_has_world_data(gm_profile_id: int) -> bool:
    for table in _CAMPAIGN_REKEY_TABLES:
        if not _regclass_exists(table):
            continue
        if not _column_exists(table, "gm_profile_id"):
            continue
        n = db.session.execute(
            text(f"SELECT 1 FROM {table} WHERE gm_profile_id = :gm LIMIT 1"),
            {"gm": gm_profile_id},
        ).first()
        if n is not None:
            return True
    return False


def _ensure_recovery_campaign_for_gm(gm_profile_id: int) -> int:
    """Return the campaign id to use for a GM, creating a Recovered Campaign if none exist."""
    row = db.session.execute(
        text(
            "SELECT id FROM campaign WHERE gm_profile_id = :gm "
            "ORDER BY created_at ASC, id ASC LIMIT 1"
        ),
        {"gm": gm_profile_id},
    ).first()
    if row is not None:
        return int(row[0])

    db.session.execute(
        text(
            "INSERT INTO campaign (gm_profile_id, name, system_type, is_active, "
            "is_free_tier, created_at, updated_at) VALUES "
            "(:gm, 'Recovered Campaign', 'generic', true, true, NOW(), NOW())"
        ),
        {"gm": gm_profile_id},
    )
    db.session.commit()
    row = db.session.execute(
        text(
            "SELECT id FROM campaign WHERE gm_profile_id = :gm "
            "ORDER BY created_at DESC, id DESC LIMIT 1"
        ),
        {"gm": gm_profile_id},
    ).first()
    log.warning(
        "preflight_campaign_rekey: created Recovered Campaign id=%s for gm_profile_id=%s",
        row[0],
        gm_profile_id,
    )
    return int(row[0])


def preflight_campaign_rekey() -> bool:
    """Backfill NULL ``campaign_id`` rows on world tables before tightening the schema.

    For each world row with ``campaign_id IS NULL``:
      - assign the GM's oldest campaign, or
      - create a "Recovered Campaign" for that GM if they have none.

    Refuses to proceed (raises) if any Player has 2+ active CampaignPlayer rows
    in different campaigns, since the new model is one-Player-per-campaign.

    Idempotent: returns True only if any DDL/DML was issued.
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("campaign"):
        return False

    patched_any = False

    if _regclass_exists("campaign_player"):
        offenders = db.session.execute(
            text(
                "SELECT player_id, COUNT(*) FROM campaign_player "
                "WHERE is_active = true GROUP BY player_id HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if offenders:
            ids = ", ".join(f"{p}({c})" for p, c in offenders)
            raise RuntimeError(
                "preflight_campaign_rekey: refusing to migrate; the following "
                f"player_ids have 2+ active campaign memberships: {ids}. "
                "Resolve in DB before continuing."
            )

    for table in _CAMPAIGN_REKEY_TABLES:
        if not _regclass_exists(table):
            continue
        if not _column_exists(table, "campaign_id"):
            continue
        if not _column_exists(table, "gm_profile_id"):
            continue

        gm_rows = db.session.execute(
            text(
                f"SELECT DISTINCT gm_profile_id FROM {table} "
                "WHERE campaign_id IS NULL AND gm_profile_id IS NOT NULL"
            )
        ).fetchall()
        for (gm_id,) in gm_rows:
            if gm_id is None:
                continue
            target_campaign = _ensure_recovery_campaign_for_gm(int(gm_id))
            res = db.session.execute(
                text(
                    f"UPDATE {table} SET campaign_id = :cid "
                    "WHERE campaign_id IS NULL AND gm_profile_id = :gm"
                ),
                {"cid": target_campaign, "gm": int(gm_id)},
            )
            rc = getattr(res, "rowcount", 0) or 0
            if rc > 0:
                patched_any = True
                log.warning(
                    "preflight_campaign_rekey: backfilled %s rows in %s for gm=%s -> campaign=%s",
                    rc,
                    table,
                    gm_id,
                    target_campaign,
                )

        # Rows that are still NULL (no gm_profile_id either) cannot be assigned;
        # delete them to satisfy the eventual NOT NULL constraint.
        res = db.session.execute(
            text(f"DELETE FROM {table} WHERE campaign_id IS NULL")
        )
        rc = getattr(res, "rowcount", 0) or 0
        if rc > 0:
            patched_any = True
            log.warning(
                "preflight_campaign_rekey: deleted %s orphaned rows from %s "
                "(no gm_profile_id, no campaign_id)",
                rc,
                table,
            )

    # ``shop_inventory`` historically inherited GM scope through ``shops`` and
    # never carried its own ``gm_profile_id`` column, so the loop above skips it.
    # Backfill ``campaign_id`` from the parent shop, then remove any orphan
    # inventory rows whose shop is itself orphaned.
    if (
        _regclass_exists("shop_inventory")
        and _regclass_exists("shops")
        and _column_exists("shop_inventory", "campaign_id")
        and _column_exists("shops", "campaign_id")
    ):
        res = db.session.execute(
            text(
                "UPDATE shop_inventory si "
                "SET campaign_id = s.campaign_id "
                "FROM shops s "
                "WHERE si.shop_id = s.shop_id "
                "AND si.campaign_id IS NULL "
                "AND s.campaign_id IS NOT NULL"
            )
        )
        rc = getattr(res, "rowcount", 0) or 0
        if rc > 0:
            patched_any = True
            log.warning(
                "preflight_campaign_rekey: backfilled %s shop_inventory rows "
                "from parent shops.campaign_id",
                rc,
            )
        res = db.session.execute(
            text("DELETE FROM shop_inventory WHERE campaign_id IS NULL")
        )
        rc = getattr(res, "rowcount", 0) or 0
        if rc > 0:
            patched_any = True
            log.warning(
                "preflight_campaign_rekey: deleted %s orphaned shop_inventory "
                "rows (parent shop missing campaign_id)",
                rc,
            )

    if patched_any:
        db.session.commit()
    return patched_any


def warn_if_preflight_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "preflight_campaign_rekey ran data backfill; review log lines for any "
            "auto-created Recovered Campaigns and re-assigned rows."
        )


def ensure_campaign_current_game_day_column() -> bool:
    """Move ``current_game_day`` from ``gm_profile`` to ``campaign``.

    Backfills each campaign with its GM's current day, then drops the old column.
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("campaign"):
        return False

    patched_any = False

    if not _column_exists("campaign", "current_game_day"):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE campaign ADD COLUMN current_game_day INTEGER NOT NULL DEFAULT 1"
            )
        )
        db.session.commit()

    if _column_exists("gm_profile", "current_game_day"):
        # Backfill: for any campaign currently at the default value (1), copy the
        # GM's current_game_day. This preserves the existing day counters for the
        # primary campaign per GM. Multiple campaigns under one GM all start the
        # same day; users can re-sync per-campaign manually if needed.
        res = db.session.execute(
            text(
                "UPDATE campaign c "
                "SET current_game_day = COALESCE(g.current_game_day, 1) "
                "FROM gm_profile g "
                "WHERE c.gm_profile_id = g.id AND c.current_game_day = 1"
            )
        )
        rc = getattr(res, "rowcount", 0) or 0
        if rc > 0:
            patched_any = True
            log.warning(
                "ensure_campaign_current_game_day_column: backfilled %s campaigns from gm_profile",
                rc,
            )
        db.session.execute(text("ALTER TABLE gm_profile DROP COLUMN current_game_day"))
        patched_any = True
        db.session.commit()

    return patched_any


def warn_if_campaign_current_game_day_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "current_game_day moved from gm_profile to campaign. Update any external "
            "tooling that read gm_profile.current_game_day directly."
        )


def ensure_campaign_debt_column() -> bool:
    """Add the per-campaign player debt toggle for existing databases."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("campaign"):
        return False
    if _column_exists("campaign", "allow_player_debt"):
        return False

    db.session.execute(
        text(
            "ALTER TABLE campaign "
            "ADD COLUMN allow_player_debt BOOLEAN NOT NULL DEFAULT FALSE"
        )
    )
    db.session.commit()
    return True


def warn_if_campaign_debt_column_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "campaign.allow_player_debt added. Existing campaigns default to Debt Off."
        )


def ensure_simulation_state_campaign_id() -> bool:
    """Re-key ``simulation_state`` from gm_profile to campaign.

    For each existing per-GM row, fan out to one row per campaign owned by that GM
    (cloning current_tick / last_tick_time; click counters land on the first only).
    Adds NOT NULL ``campaign_id`` and drops ``gm_profile_id``.
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("simulation_state"):
        return False

    patched_any = False

    if not _column_exists("simulation_state", "campaign_id"):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE simulation_state ADD COLUMN campaign_id INTEGER "
                "REFERENCES campaign(id) ON DELETE CASCADE"
            )
        )
        db.session.commit()

    if _column_exists("simulation_state", "gm_profile_id"):
        # Drop any legacy uniqueness on (gm_profile_id) that would block fan-out
        # INSERTs cloning a row across multiple campaigns owned by the same GM.
        # The new uniqueness on (campaign_id) is added at the end of this helper.
        db.session.execute(
            text(
                "ALTER TABLE simulation_state "
                "DROP CONSTRAINT IF EXISTS uq_simulation_state_gm_profile_id"
            )
        )
        db.session.execute(
            text("DROP INDEX IF EXISTS uq_simulation_state_gm_profile_id")
        )
        db.session.execute(
            text("DROP INDEX IF EXISTS ix_simulation_state_gm_profile_id")
        )
        db.session.commit()

        # Backfill: for each row in simulation_state, locate the GM's campaigns.
        # If exactly one campaign exists, set campaign_id directly. If multiple,
        # set the original row to the oldest, and clone for the rest (zeroed
        # click counters; current_tick/last_tick_time copied so all campaigns
        # start at the same place).
        rows = db.session.execute(
            text(
                "SELECT state_id, gm_profile_id, current_tick, speed, last_tick_time, "
                "sim_clicks_day, sim_clicks_week, sim_clicks_month, sim_clicks_year, "
                "sim_clicks_pause FROM simulation_state WHERE campaign_id IS NULL"
            )
        ).fetchall()
        for r in rows:
            sid, gm_id, tick, speed, last_tick, c_d, c_w, c_m, c_y, c_p = r
            if gm_id is None:
                db.session.execute(
                    text("DELETE FROM simulation_state WHERE state_id = :sid"),
                    {"sid": sid},
                )
                continue
            camps = db.session.execute(
                text(
                    "SELECT id FROM campaign WHERE gm_profile_id = :gm "
                    "ORDER BY created_at ASC, id ASC"
                ),
                {"gm": gm_id},
            ).fetchall()
            camp_ids = [int(x[0]) for x in camps]
            if not camp_ids:
                # GM has no campaign and a Recovered Campaign was not created
                # for them by preflight (no world data). Drop the orphan state.
                db.session.execute(
                    text("DELETE FROM simulation_state WHERE state_id = :sid"),
                    {"sid": sid},
                )
                continue

            db.session.execute(
                text(
                    "UPDATE simulation_state SET campaign_id = :cid WHERE state_id = :sid"
                ),
                {"cid": camp_ids[0], "sid": sid},
            )
            for cid in camp_ids[1:]:
                db.session.execute(
                    text(
                        "INSERT INTO simulation_state "
                        "(current_tick, speed, last_tick_time, gm_profile_id, "
                        "sim_clicks_day, sim_clicks_week, sim_clicks_month, "
                        "sim_clicks_year, sim_clicks_pause, campaign_id) VALUES "
                        "(:tick, :speed, :last_tick, :gm, 0, 0, 0, 0, 0, :cid)"
                    ),
                    {
                        "tick": tick,
                        "speed": speed,
                        "last_tick": last_tick,
                        "gm": gm_id,
                        "cid": cid,
                    },
                )
        if rows:
            patched_any = True
        db.session.commit()

        # All rows now have campaign_id set; tighten and drop legacy column.
        db.session.execute(
            text(
                "DELETE FROM simulation_state WHERE campaign_id IS NULL"
            )
        )
        db.session.execute(
            text(
                "ALTER TABLE simulation_state ALTER COLUMN campaign_id SET NOT NULL"
            )
        )
        db.session.execute(
            text("ALTER TABLE simulation_state DROP COLUMN gm_profile_id")
        )
        db.session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_simulation_state_campaign "
                "ON simulation_state (campaign_id)"
            )
        )
        patched_any = True
        db.session.commit()

    return patched_any


def warn_if_simulation_state_campaign_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "simulation_state re-keyed to campaign_id. Existing per-GM tick state "
            "was cloned across the GM's campaigns; verify per-campaign tick counts."
        )


def ensure_gm_world_state_campaign_id() -> bool:
    """Re-key ``gm_world_state`` PK from gm_profile_id to campaign_id."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("gm_world_state"):
        return False

    patched_any = False

    if not _column_exists("gm_world_state", "campaign_id"):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE gm_world_state ADD COLUMN campaign_id INTEGER "
                "REFERENCES campaign(id) ON DELETE CASCADE"
            )
        )
        db.session.commit()

    if _column_exists("gm_world_state", "gm_profile_id"):
        # The legacy primary key on (gm_profile_id) would block fan-out INSERTs
        # cloning a row across multiple campaigns owned by the same GM. Drop it
        # now; the new PK on (campaign_id) is recreated after the backfill.
        db.session.execute(
            text(
                "ALTER TABLE gm_world_state DROP CONSTRAINT IF EXISTS gm_world_state_pkey"
            )
        )
        db.session.execute(
            text("DROP INDEX IF EXISTS uq_gm_world_state_gm_profile_id")
        )
        db.session.commit()

        rows = db.session.execute(
            text(
                "SELECT gm_profile_id, state_json, schema_version, tick_seq, "
                "tick_generation_id, updated_at FROM gm_world_state "
                "WHERE campaign_id IS NULL"
            )
        ).fetchall()
        for r in rows:
            gm_id, state_json, sver, tick_seq, gen_id, updated_at = r
            if gm_id is None:
                continue
            camps = db.session.execute(
                text(
                    "SELECT id FROM campaign WHERE gm_profile_id = :gm "
                    "ORDER BY created_at ASC, id ASC"
                ),
                {"gm": gm_id},
            ).fetchall()
            camp_ids = [int(x[0]) for x in camps]
            if not camp_ids:
                continue
            db.session.execute(
                text(
                    "UPDATE gm_world_state SET campaign_id = :cid "
                    "WHERE gm_profile_id = :gm AND campaign_id IS NULL"
                ),
                {"cid": camp_ids[0], "gm": gm_id},
            )
            # psycopg2 cannot adapt a Python dict to a JSON column without an
            # explicit cast, so serialize and CAST the parameter to JSON.
            sj_payload = (
                json.dumps(state_json)
                if isinstance(state_json, (dict, list))
                else state_json
            )
            for cid in camp_ids[1:]:
                db.session.execute(
                    text(
                        "INSERT INTO gm_world_state "
                        "(gm_profile_id, campaign_id, state_json, schema_version, "
                        "tick_seq, tick_generation_id, updated_at) VALUES "
                        "(:gm, :cid, CAST(:sj AS JSON), :sv, :ts, :tg, :up)"
                    ),
                    {
                        "gm": gm_id,
                        "cid": cid,
                        "sj": sj_payload,
                        "sv": sver,
                        "ts": tick_seq,
                        "tg": gen_id,
                        "up": updated_at,
                    },
                )
        if rows:
            patched_any = True
        db.session.commit()

        # Drop rows still missing a campaign_id (no campaigns owned by GM).
        db.session.execute(
            text("DELETE FROM gm_world_state WHERE campaign_id IS NULL")
        )

        # Swap PK from gm_profile_id to campaign_id.
        db.session.execute(
            text(
                "ALTER TABLE gm_world_state DROP CONSTRAINT IF EXISTS gm_world_state_pkey"
            )
        )
        db.session.execute(
            text(
                "ALTER TABLE gm_world_state ALTER COLUMN campaign_id SET NOT NULL"
            )
        )
        db.session.execute(
            text(
                "ALTER TABLE gm_world_state ADD CONSTRAINT gm_world_state_pkey "
                "PRIMARY KEY (campaign_id)"
            )
        )
        db.session.execute(
            text("ALTER TABLE gm_world_state DROP COLUMN gm_profile_id")
        )
        patched_any = True
        db.session.commit()

    return patched_any


def warn_if_gm_world_state_campaign_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "gm_world_state re-keyed to campaign_id (PK). Cached snapshots are "
            "now per-campaign instead of per-GM."
        )


def ensure_player_campaign_id() -> bool:
    """Add ``Player.campaign_id`` (nullable; NULL = solo vault) and backfill.

    Backfills from active ``CampaignPlayer`` rows. Drops ``Player.gm_profile_id``.
    Players with ``gm_profile_id IS NOT NULL`` but no membership become solo
    (campaign_id NULL).
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("player"):
        return False

    patched_any = False

    if not _column_exists("player", "campaign_id"):
        patched_any = True
        db.session.execute(
            text(
                "ALTER TABLE player ADD COLUMN campaign_id INTEGER "
                "REFERENCES campaign(id) ON DELETE SET NULL"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_player_campaign_id "
                "ON player (campaign_id)"
            )
        )
        db.session.commit()

    if _regclass_exists("campaign_player"):
        res = db.session.execute(
            text(
                "UPDATE player p "
                "SET campaign_id = cp.campaign_id "
                "FROM campaign_player cp "
                "WHERE cp.player_id = p.id AND cp.is_active = true "
                "AND p.campaign_id IS NULL"
            )
        )
        rc = getattr(res, "rowcount", 0) or 0
        if rc > 0:
            patched_any = True
            log.warning(
                "ensure_player_campaign_id: backfilled %s player(s) from campaign_player",
                rc,
            )
        db.session.commit()

    if _column_exists("player", "gm_profile_id"):
        # Drop relationships to gm_profile that are no longer authoritative.
        # The column drops cascade FKs but we run the explicit DROP for clarity.
        db.session.execute(
            text(
                "ALTER TABLE player DROP COLUMN gm_profile_id"
            )
        )
        patched_any = True
        db.session.commit()

    return patched_any


def warn_if_player_campaign_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "Player table re-keyed to campaign_id (nullable=solo). "
            "gm_profile_id removed; CampaignPlayer is now redundant."
        )


def drop_campaign_player_table() -> bool:
    """Drop the now-redundant ``campaign_player`` table."""
    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("campaign_player"):
        return False
    db.session.execute(text("DROP TABLE campaign_player"))
    db.session.commit()
    log.warning("drop_campaign_player_table: campaign_player table removed")
    return True


def warn_if_campaign_player_dropped(applied: bool) -> None:
    if applied:
        log.warning(
            "campaign_player table dropped. Player.campaign_id is the sole "
            "source of campaign membership going forward."
        )


def ensure_world_tables_campaign_only() -> bool:
    """Drop ``gm_profile_id`` and enforce NOT NULL ``campaign_id`` on world tables.

    Called after :func:`preflight_campaign_rekey` has backfilled NULLs.
    Idempotent.
    """
    if db.engine.dialect.name != "postgresql":
        return False

    patched_any = False
    for table in _CAMPAIGN_REKEY_TABLES:
        if not _regclass_exists(table):
            continue
        if _column_exists(table, "campaign_id"):
            null_state = db.session.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :t "
                    "AND column_name = 'campaign_id'"
                ),
                {"t": table},
            ).first()
            if null_state and (null_state[0] or "").upper() == "YES":
                patched_any = True
                db.session.execute(
                    text(
                        f"ALTER TABLE {table} ALTER COLUMN campaign_id SET NOT NULL"
                    )
                )
        if _column_exists(table, "gm_profile_id"):
            patched_any = True
            db.session.execute(text(f"ALTER TABLE {table} DROP COLUMN gm_profile_id"))
        if patched_any:
            db.session.commit()
    return patched_any


def warn_if_world_tables_campaign_only_applied(patched_any: bool) -> None:
    if patched_any:
        log.warning(
            "World tables re-keyed: campaign_id NOT NULL, gm_profile_id removed. "
            "Queries now scope strictly by campaign."
        )


def ensure_simulation_logs_table() -> bool:
    """Create ``simulation_logs`` if missing.

    The model has always declared this table, but in some environments it was
    never created by Alembic; deletes of a Campaign then fail with
    ``relation "simulation_logs" does not exist`` because SQLAlchemy lazy-loads
    the ``Campaign.simulation_logs`` backref. Idempotent.
    """
    if db.engine.dialect.name != "postgresql":
        return False
    if _regclass_exists("simulation_logs"):
        return False
    db.session.execute(
        text(
            "CREATE TABLE simulation_logs ("
            "log_id SERIAL PRIMARY KEY, "
            "tick_id INTEGER NOT NULL, "
            "timestamp TIMESTAMP NOT NULL DEFAULT NOW(), "
            "event_type VARCHAR(50) NOT NULL, "
            "details JSON NOT NULL, "
            "campaign_id INTEGER NOT NULL REFERENCES campaign(id) ON DELETE CASCADE"
            ")"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_simulation_logs_campaign_id "
            "ON simulation_logs (campaign_id)"
        )
    )
    db.session.commit()
    return True


def warn_if_simulation_logs_table_created(applied: bool) -> None:
    if applied:
        log.warning(
            "simulation_logs table created (was missing). The /api/simulation/logs "
            "endpoint and Campaign delete cascade now have a backing table."
        )


def ensure_sim_rules_table() -> bool:
    """Create ``sim_rules`` if missing. Same rationale as simulation_logs."""
    if db.engine.dialect.name != "postgresql":
        return False
    if _regclass_exists("sim_rules"):
        return False
    db.session.execute(
        text(
            "CREATE TABLE sim_rules ("
            "rule_id SERIAL PRIMARY KEY, "
            "rule_type VARCHAR(50) NOT NULL, "
            "target_type VARCHAR(50) NOT NULL, "
            "function_type VARCHAR(50) NOT NULL, "
            "condition_json JSON NOT NULL, "
            "campaign_id INTEGER NOT NULL REFERENCES campaign(id) ON DELETE CASCADE"
            ")"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_sim_rules_campaign_id "
            "ON sim_rules (campaign_id)"
        )
    )
    db.session.commit()
    return True


def warn_if_sim_rules_table_created(applied: bool) -> None:
    if applied:
        log.warning(
            "sim_rules table created (was missing). Campaign delete cascade now "
            "has a backing table for sim rules."
        )


def ensure_deleted_campaign_sim_snapshot_table() -> bool:
    """Create ``deleted_campaign_sim_snapshot`` if missing.

    Tombstone rows for the GM simulation usage analytics view: when a
    Campaign is deleted, its final per-campaign metrics are archived here
    so the vault-keeper dashboard retains historical totals per GM. The
    FK to ``gm_profile`` cascades, so deleting a GM also drops their
    snapshots (per-GM analytics has no meaning without the GM). There
    is intentionally no FK back to ``campaign`` because the parent is
    expected to be gone by the time these rows are read.
    """

    if db.engine.dialect.name != "postgresql":
        return False
    if _regclass_exists("deleted_campaign_sim_snapshot"):
        return False
    db.session.execute(
        text(
            "CREATE TABLE deleted_campaign_sim_snapshot ("
            "snapshot_id SERIAL PRIMARY KEY, "
            "gm_profile_id INTEGER NOT NULL REFERENCES gm_profile(id) ON DELETE CASCADE, "
            "campaign_id INTEGER NOT NULL, "
            "campaign_name VARCHAR(120) NOT NULL, "
            "system_type VARCHAR(50) NOT NULL DEFAULT 'generic', "
            "campaign_created_at TIMESTAMP NULL, "
            "deleted_at TIMESTAMP NOT NULL DEFAULT NOW(), "
            "current_game_day INTEGER NOT NULL DEFAULT 1, "
            "days_simulated INTEGER NOT NULL DEFAULT 0, "
            "sim_clicks_day INTEGER NOT NULL DEFAULT 0, "
            "sim_clicks_week INTEGER NOT NULL DEFAULT 0, "
            "sim_clicks_month INTEGER NOT NULL DEFAULT 0, "
            "sim_clicks_year INTEGER NOT NULL DEFAULT 0, "
            "sim_clicks_pause INTEGER NOT NULL DEFAULT 0, "
            "last_tick_time TIMESTAMP NULL"
            ")"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_deleted_campaign_sim_snapshot_gm_profile "
            "ON deleted_campaign_sim_snapshot (gm_profile_id)"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_deleted_campaign_sim_snapshot_campaign "
            "ON deleted_campaign_sim_snapshot (campaign_id)"
        )
    )
    db.session.commit()
    return True


def warn_if_deleted_campaign_sim_snapshot_table_created(applied: bool) -> None:
    if applied:
        log.warning(
            "deleted_campaign_sim_snapshot table created. GM simulation usage "
            "analytics will now retain per-campaign metrics across Campaign deletes."
        )


def ensure_region_campaign_only() -> bool:
    """Align the live ``region`` table with the campaign-only ORM model.

    ``region`` was missed by ``_CAMPAIGN_REKEY_TABLES`` so the standard
    rekey path never touched it. The current model declares a single
    composite unique constraint ``uq_region_campaign_name`` on
    ``(campaign_id, name)`` and an FK ``campaign_id → campaign(id)
    ON DELETE CASCADE``. Older deployments may still carry any of:

    * a legacy ``gm_profile_id`` column,
    * a legacy unique constraint on ``(gm_profile_id, name)``,
    * a legacy unique constraint on ``name`` alone,
    * an FK on ``campaign_id`` without ``ON DELETE CASCADE``.

    Any of these would manifest as a ``psycopg2.errors.UniqueViolation``
    or ``ForeignKeyViolation`` when the world generator inserts regions
    for a freshly created Campaign — exactly the user-visible
    "Name conflict detected" symptom. This helper is idempotent: every
    step is gated on a presence check so re-running is a no-op.
    """

    if db.engine.dialect.name != "postgresql":
        return False
    if not _regclass_exists("region"):
        return False

    patched_any = False

    # 1) Drop legacy single-column unique on `name` if present. SQLAlchemy
    #    historically may have created `uq_region_name` when the model had
    #    a global unique on name. We need composite scoping now.
    legacy_name_only = db.session.execute(
        text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class cl ON cl.oid = con.conrelid "
            "WHERE cl.relname = 'region' AND con.contype = 'u' "
            "AND (SELECT count(*) FROM unnest(con.conkey)) = 1 "
            "AND EXISTS ("
            "  SELECT 1 FROM pg_attribute a "
            "  WHERE a.attrelid = cl.oid AND a.attnum = ANY(con.conkey) "
            "  AND a.attname = 'name'"
            ")"
        )
    ).fetchall()
    for (cname,) in legacy_name_only:
        patched_any = True
        log.warning("Dropping legacy region unique constraint: %s", cname)
        db.session.execute(text(f'ALTER TABLE region DROP CONSTRAINT "{cname}"'))

    # 2) Drop legacy composite unique on (gm_profile_id, name) if present.
    legacy_gm_name = db.session.execute(
        text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class cl ON cl.oid = con.conrelid "
            "WHERE cl.relname = 'region' AND con.contype = 'u' "
            "AND con.conkey @> ARRAY["
            "  (SELECT a.attnum FROM pg_attribute a "
            "   WHERE a.attrelid = cl.oid AND a.attname = 'gm_profile_id')"
            "]::int2[]"
        )
    ).fetchall()
    for (cname,) in legacy_gm_name:
        patched_any = True
        log.warning("Dropping legacy region (gm_profile_id, ...) unique constraint: %s", cname)
        db.session.execute(text(f'ALTER TABLE region DROP CONSTRAINT "{cname}"'))

    # 3) Drop legacy `gm_profile_id` column if it exists. CASCADE here
    #    guarantees any remaining indexes/constraints on the column are
    #    dropped along with the column itself.
    if _column_exists("region", "gm_profile_id"):
        patched_any = True
        log.warning("Dropping legacy region.gm_profile_id column")
        db.session.execute(
            text("ALTER TABLE region DROP COLUMN gm_profile_id CASCADE")
        )

    # 4) Ensure the FK on campaign_id has ON DELETE CASCADE. If the live
    #    FK was created NO ACTION (older db.create_all paths), recreate it.
    if _column_exists("region", "campaign_id"):
        fk_rows = db.session.execute(
            text(
                "SELECT con.conname, con.confdeltype FROM pg_constraint con "
                "JOIN pg_class cl ON cl.oid = con.conrelid "
                "WHERE cl.relname = 'region' AND con.contype = 'f' "
                "AND con.conkey @> ARRAY["
                "  (SELECT a.attnum FROM pg_attribute a "
                "   WHERE a.attrelid = cl.oid AND a.attname = 'campaign_id')"
                "]::int2[]"
            )
        ).fetchall()
        for cname, confdeltype in fk_rows:
            # 'c' is CASCADE in pg_constraint.confdeltype.
            if (confdeltype or "").lower() != "c":
                patched_any = True
                log.warning(
                    "Recreating region.campaign_id FK %s with ON DELETE CASCADE", cname
                )
                db.session.execute(
                    text(f'ALTER TABLE region DROP CONSTRAINT "{cname}"')
                )
                db.session.execute(
                    text(
                        "ALTER TABLE region ADD CONSTRAINT region_campaign_id_fkey "
                        "FOREIGN KEY (campaign_id) REFERENCES campaign(id) "
                        "ON DELETE CASCADE"
                    )
                )

    # 5) Ensure the model's composite unique exists. If a previous boot
    #    dropped a legacy unique without recreating the new one, world-gen
    #    would silently allow duplicates. Idempotent: skip if present.
    have_composite = db.session.execute(
        text(
            "SELECT 1 FROM pg_constraint con "
            "JOIN pg_class cl ON cl.oid = con.conrelid "
            "WHERE cl.relname = 'region' AND con.contype = 'u' "
            "AND con.conname = 'uq_region_campaign_name'"
        )
    ).first()
    if not have_composite:
        patched_any = True
        log.warning("Creating uq_region_campaign_name composite unique")
        db.session.execute(
            text(
                "ALTER TABLE region ADD CONSTRAINT uq_region_campaign_name "
                "UNIQUE (campaign_id, name)"
            )
        )

    if patched_any:
        db.session.commit()
    return patched_any


def warn_if_region_campaign_only_applied(applied: bool) -> None:
    if applied:
        log.warning(
            "region table aligned to campaign-only model: legacy gm_profile_id "
            "column/constraints removed, FK CASCADE confirmed, "
            "uq_region_campaign_name in place. World generation should now "
            "succeed for fresh campaigns."
        )


def ensure_shop_next_restock_day_column() -> bool:
    """Add shops.next_restock_day when missing (dev / pre-migration DBs)."""
    dialect = db.engine.dialect.name
    if dialect == "sqlite":
        if not _sqlite_table_exists("shops"):
            return False
        if _sqlite_column_exists("shops", "next_restock_day"):
            return False
        db.session.execute(text("ALTER TABLE shops ADD COLUMN next_restock_day INTEGER"))
        db.session.commit()
        return True

    if dialect != "postgresql":
        return False

    if not _regclass_exists("shops"):
        return False
    if _column_exists("shops", "next_restock_day"):
        return False
    db.session.execute(text("ALTER TABLE shops ADD COLUMN next_restock_day INTEGER"))
    db.session.commit()
    return True


def warn_if_shop_next_restock_day_applied(applied: bool) -> None:
    if applied:
        log.warning(
            "shops.next_restock_day added via schema_compat; "
            "run sql/shops_next_restock_day.sql in production."
        )
