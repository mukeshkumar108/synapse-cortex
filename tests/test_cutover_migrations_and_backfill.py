"""Schema parity + reversibility of migrations 0032-0034, and the idempotent
backfill (dry-run included). Migrations are exercised directly through
Alembic operations on a scratch SQLite database."""
import importlib.util
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import SQLModel, select

from src.db import async_session_maker
from tests.cortex_fixtures import NOW, USER, WS, build_longitudinal_world

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
NEW_TABLES = ["matters", "matter_links", "matter_relations", "world_model_snapshots",
              "knowledge_coverage", "session_episodes"]
ADDED = {"model_entries": {"claim_kind", "subject_matter_id", "epistemic_status", "evidence_refs_json",
                           "holder_actor", "direction"},
         "expectations": {"direction"}, "open_loops": {"direction"}, "commitment_candidates": {"direction"}}


def load(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def baseline(conn):
    """Minimal pre-cutover tables the migrations alter (id only is enough)."""
    for t in ADDED:
        conn.execute(sa.text(f"CREATE TABLE {t} (id CHAR(32) PRIMARY KEY)"))


def cols(conn, table):
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def test_migration_chain_is_linear_from_0031():
    revs = {}
    for f in VERSIONS.glob("00*.py"):
        m = load(f.stem)
        revs[m.revision] = m.down_revision
    assert revs["0032_matters"] == "0031_consolidation_runs"
    assert revs["0033_epistemic_direction"] == "0032_matters"
    assert revs["0034_world_model_coverage"] == "0033_epistemic_direction"
    downs = list(revs.values())
    assert len(downs) == len(set(downs)), "branching migration history"


def test_upgrade_matches_models_and_downgrade_restores_prior_schema():
    m32, m33, m34 = (load(n) for n in ("0032_matters", "0033_epistemic_direction",
                                       "0034_world_model_coverage"))
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        baseline(conn)
        with Operations.context(MigrationContext.configure(conn)):
            for m in (m32, m33, m34):
                m.upgrade()
        tables = set(sa.inspect(conn).get_table_names())
        meta = SQLModel.metadata
        for t in NEW_TABLES:
            assert t in tables, t
            assert cols(conn, t) == {c.name for c in meta.tables[t].columns}, f"column drift in {t}"
        for t, added in ADDED.items():
            assert added <= cols(conn, t), t
            assert added <= {c.name for c in meta.tables[t].columns}
        # bounded vocabularies are enforced by the database, not just the app
        conn.execute(sa.text("INSERT INTO matters (id, honcho_workspace_id, kind, title, canonical_key, status, "
                             "first_seen, active_since, last_touched, confidence, formation, salience_components_json, "
                             "created_at, updated_at) VALUES ('a','w','other','t','','active',"
                             "'2026-01-01','2026-01-01','2026-01-01',0.5,'inferred','{}','2026-01-01','2026-01-01')"))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("INSERT INTO matter_relations (id, honcho_workspace_id, from_matter_id, to_matter_id,"
                                 " rel_type, evidence_refs_json, formation, confidence, created_at) VALUES "
                                 "('r','w','a','b','blocks','[]','x',0.5,'2026-01-01')"))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("INSERT INTO knowledge_coverage (id, honcho_workspace_id, subject_key, status, source,"
                                 " basis, evidence_count, evidence_refs_json, why_useful, updated_at, created_at) VALUES "
                                 "('k','w','x','guess','derived','',0,'[]','','2026-01-01','2026-01-01')"))
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            for m in (m34, m33, m32):
                m.downgrade()
        assert not set(NEW_TABLES) & set(sa.inspect(conn).get_table_names())
        for t in ADDED:
            assert cols(conn, t) == {"id"}, t          # additive columns fully removed


def test_migrations_never_drop_or_rewrite_existing_data():
    for name in ("0032_matters", "0033_epistemic_direction", "0034_world_model_coverage"):
        src = (VERSIONS / f"{name}.py").read_text()
        up = src.split("def downgrade")[0]
        assert "drop_" not in up and "execute(" not in up and "update" not in up.lower().replace("updated_at", ""), name


def load_script():
    spec = importlib.util.spec_from_file_location("backfill_matters", ROOT / "scripts" / "backfill_matters.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_backfill_seeds_matters_directions_coverage_and_world_model_idempotently():
    from sqlalchemy import text
    from src.models.expectation import Expectation
    from src.models.matter import Matter
    from src.models.world_model import KnowledgeCoverage, WorldModelSnapshot
    await build_longitudinal_world()
    async with async_session_maker() as db:     # simulate pre-cutover rows: no direction, no matters, no snapshot
        for t in ("expectations", "open_loops", "commitment_candidates"):
            await db.execute(text(f"UPDATE {t} SET direction = NULL"))
        for t in ("matter_relations", "matter_links", "matters", "world_model_snapshots", "knowledge_coverage"):
            await db.execute(text(f"DELETE FROM {t}"))
        await db.execute(text("DELETE FROM entity_links WHERE object_type = 'matter'"))
        await db.commit()
    script = load_script()
    now = NOW.replace(tzinfo=None)

    async def run(dry):
        from contextlib import aclosing
        from src.db import get_rollback_session
        if dry:
            async with aclosing(get_rollback_session()) as gen:   # always finalise: releases the SQLite lock
                db = await gen.__anext__()
                return await script.backfill_workspace(db, WS, now=now, tz="Europe/London", allow_judge=False)
        async with async_session_maker() as db:
            return await script.backfill_workspace(db, WS, now=now, tz="Europe/London", allow_judge=False)

    dry = await run(True)
    assert dry["directions_stamped"]["expectations"] > 0
    async with async_session_maker() as db:     # dry run changed nothing
        assert not (await db.execute(select(Matter))).scalars().all()
        assert not (await db.execute(select(WorldModelSnapshot))).scalars().all()
        assert all(e.direction is None for e in (await db.execute(select(Expectation))).scalars().all())
    real = await run(False)
    ws_report = real["world_models"][USER]
    assert ws_report["active_matters"] >= 8 and ws_report["model_version"] == "world-model-v1"
    assert "known" in ws_report["coverage"] and "unknown" in ws_report["coverage"]
    async with async_session_maker() as db:
        assert all(e.direction for e in (await db.execute(select(Expectation))).scalars().all())
        n_matters = len((await db.execute(select(Matter))).scalars().all())
        assert (await db.execute(select(KnowledgeCoverage))).scalars().all()
    again = await run(False)                    # re-runnable: nothing new, no duplicate Matters
    async with async_session_maker() as db:
        assert len((await db.execute(select(Matter))).scalars().all()) == n_matters
    assert sum(v["created"] for v in again["matters"].values()) == 0
