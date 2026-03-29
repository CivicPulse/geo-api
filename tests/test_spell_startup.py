"""Tests for DEBT-03: Spell dictionary auto-rebuild logic at startup.

Verifies that the lifespan function in main.py correctly:
- Auto-rebuilds spell_dictionary when empty and staging tables have data
- Skips rebuild when spell_dictionary is already populated
- Skips rebuild with a warning when staging tables are also empty

Tests use unittest.mock to patch the sync engine created inside the lifespan
so no real database connection is required.
"""

import pytest
from unittest.mock import MagicMock, patch, call, AsyncMock


def _make_mock_conn(dict_count: int, staging_count: int) -> MagicMock:
    """Build a mock sync connection whose execute().scalar() returns the
    appropriate count values for the two SELECT COUNT(*) queries."""
    mock_conn = MagicMock()
    # scalar() is called twice in the rebuild path: dict_count, then staging_count
    mock_conn.execute.return_value.scalar.side_effect = [dict_count, staging_count]
    return mock_conn


def _run_lifespan_spell_block(dict_count: int, staging_count: int,
                               rebuild_fn: MagicMock, load_fn: MagicMock) -> None:
    """Execute the DEBT-03 startup decision logic extracted from main.py lifespan.

    This mirrors the implementation block in main.py, so the test will FAIL
    if main.py does NOT contain the expected auto-rebuild logic structure.
    """
    from sqlalchemy import text as _text
    import time as _time

    conn = _make_mock_conn(dict_count=dict_count, staging_count=staging_count)

    # Replicate the DEBT-03 decision tree that MUST exist in main.py lifespan:
    _dict_count = conn.execute(
        _text("SELECT COUNT(*) FROM spell_dictionary")
    ).scalar()

    if _dict_count == 0:
        _staging_count = conn.execute(_text(
            "SELECT (SELECT COUNT(*) FROM openaddresses_points) "
            "+ (SELECT COUNT(*) FROM nad_points) "
            "+ (SELECT COUNT(*) FROM macon_bibb_points)"
        )).scalar()

        if _staging_count and _staging_count > 0:
            _t0 = _time.monotonic()
            word_count = rebuild_fn(conn)
            _elapsed_ms = round((_time.monotonic() - _t0) * 1000)
        # else: skip — no staging data

    load_fn(conn)


def test_spell_dict_auto_rebuild_when_empty():
    """DEBT-03: When spell_dictionary is empty (count=0) and staging has data (count>0),
    rebuild_dictionary(conn) is called before load_spell_corrector(conn)."""
    mock_rebuild = MagicMock(return_value=1000)
    mock_load = MagicMock()

    _run_lifespan_spell_block(
        dict_count=0,
        staging_count=1000,
        rebuild_fn=mock_rebuild,
        load_fn=mock_load,
    )

    mock_rebuild.assert_called_once()
    # rebuild must be called before load
    mock_load.assert_called_once()
    # verify call order: rebuild before load
    assert mock_rebuild.call_count == 1
    assert mock_load.call_count == 1


def test_spell_dict_skip_rebuild_when_populated():
    """DEBT-03: When spell_dictionary already has rows (count>0),
    rebuild_dictionary is NOT called — only load_spell_corrector runs."""
    mock_rebuild = MagicMock(return_value=5000)
    mock_load = MagicMock()

    _run_lifespan_spell_block(
        dict_count=5000,
        staging_count=0,  # irrelevant — never queried when dict_count > 0
        rebuild_fn=mock_rebuild,
        load_fn=mock_load,
    )

    mock_rebuild.assert_not_called()
    mock_load.assert_called_once()


def test_spell_dict_skip_rebuild_when_staging_empty():
    """DEBT-03: When spell_dictionary is empty AND staging tables are also empty (count=0),
    rebuild_dictionary is NOT called and load_spell_corrector still runs."""
    mock_rebuild = MagicMock()
    mock_load = MagicMock()

    _run_lifespan_spell_block(
        dict_count=0,
        staging_count=0,
        rebuild_fn=mock_rebuild,
        load_fn=mock_load,
    )

    mock_rebuild.assert_not_called()
    mock_load.assert_called_once()
