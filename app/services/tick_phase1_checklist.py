"""Phase 1 validation checklist (from state-object migration plan). Not executed automatically."""

PHASE1_VALIDATION_CHECKLIST = (
    "Performance: t_load, t_compute, t_flush, t_persist in stats; no SQL during compute loop (autoflush off).",
    "Performance: session_dirty_count / session_new_count recorded; t_orm_pressure alias for compute window.",
    "Consistency: current_game_day only persisted on successful commit; rollback restores prior day.",
    "Consistency: SimulationState.current_tick aligned with Campaign.current_game_day on tick.",
    "Schema: gm_world_state exists; tick_seq / tick_generation_id written when WORLD_STATE_ENABLED.",
    "Safety: WORLD_STATE_ENABLED defaults True (opt out with env false); READ_PRICES_FROM_WORLD_STATE only after blob populated.",
    "Dual-write: enabling READ without WORLD_STATE writes risks stale blob vs rows — document for operators.",
)
