"""Unit tests for SpellCorrector, rebuild_dictionary, and load_spell_corrector.

TDD RED phase: These tests will fail until Task 2 implements the spell module.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from symspellpy import SymSpell, Verbosity


def _build_sym_spell(words: list[str]) -> SymSpell:
    """Helper: create a SymSpell object pre-loaded with test vocabulary."""
    sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    for word in words:
        sym_spell.create_dictionary_entry(word.upper(), 10)
    return sym_spell


TEST_VOCAB = ["MERCER", "MARTIN", "LUTHER", "KING", "VINEVILLE", "RIVERSIDE"]


# ===================================================================
# SpellCorrector.correct_street_name tests
# ===================================================================

class TestCorrectStreetName:
    def _make_corrector(self, words=None):
        from civpulse_geo.spell.corrector import SpellCorrector
        sym_spell = _build_sym_spell(words or TEST_VOCAB)
        return SpellCorrector(sym_spell)

    def test_single_typo_corrected(self):
        """D-01: single-char typo should be corrected (MRCCER → MERCER)."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("MRCCER")
        assert result == "MERCER"

    def test_multi_word_correction(self):
        """D-02: multi-word street names corrected per-word independently."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("MAARTIN LTHER KING")
        # Each token corrected independently: MAARTIN→MARTIN, LTHER→LUTHER, KING stays
        assert result == "MARTIN LUTHER KING"

    def test_short_token_elm_unchanged(self):
        """D-04: tokens < 4 chars pass through uncorrected (ELM is 3 chars)."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("ELM")
        assert result == "ELM"

    def test_short_token_oak_unchanged(self):
        """D-04: tokens < 4 chars pass through uncorrected (OAK is 3 chars)."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("OAK")
        assert result == "OAK"

    def test_empty_string_returns_empty(self):
        """Empty input returns empty string without error."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("")
        assert result == ""

    def test_none_like_falsy_handled(self):
        """Falsy input returns the input unchanged (D-04 edge case)."""
        corrector = self._make_corrector()
        # Passing None would be a type error, but empty string is the falsy case
        result = corrector.correct_street_name("")
        assert result == ""

    def test_correct_word_unchanged(self):
        """Words already correct pass through without modification."""
        corrector = self._make_corrector()
        result = corrector.correct_street_name("MERCER")
        assert result == "MERCER"

    def test_mixed_short_and_long_tokens(self):
        """Mixed tokens: short ones pass through, long ones get corrected."""
        corrector = self._make_corrector()
        # "ST" is 2 chars (passes through), "MRCCER" is 6 chars (corrected)
        result = corrector.correct_street_name("MRCCER ST")
        assert "MERCER" in result
        assert "ST" in result


# ===================================================================
# rebuild_dictionary tests
# ===================================================================

class TestRebuildDictionary:
    def _make_mock_conn(self, words=None):
        """Create a mock database connection for rebuild_dictionary tests."""
        mock_conn = MagicMock()
        # Default: execute returns a result with rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_conn.execute.return_value = mock_result
        return mock_conn

    def test_truncate_called_first(self):
        """rebuild_dictionary must TRUNCATE spell_dictionary before inserting."""
        from civpulse_geo.spell.corrector import rebuild_dictionary
        from sqlalchemy import text

        mock_conn = self._make_mock_conn()
        rebuild_dictionary(mock_conn)

        # First execute call should be TRUNCATE
        first_call_args = mock_conn.execute.call_args_list[0]
        sql_str = str(first_call_args[0][0])
        assert "TRUNCATE" in sql_str.upper() or "TRUNCATE" in str(first_call_args).upper()

    def test_insert_called_after_truncate(self):
        """INSERT is called after TRUNCATE."""
        from civpulse_geo.spell.corrector import rebuild_dictionary

        mock_conn = self._make_mock_conn()
        rebuild_dictionary(mock_conn)

        # Should have at least 2 execute calls (TRUNCATE + INSERT)
        assert mock_conn.execute.call_count >= 2

    def test_commit_called(self):
        """rebuild_dictionary commits after insert."""
        from civpulse_geo.spell.corrector import rebuild_dictionary

        mock_conn = self._make_mock_conn()
        rebuild_dictionary(mock_conn)

        mock_conn.commit.assert_called()

    def test_returns_rowcount(self):
        """rebuild_dictionary returns the rowcount of inserted words."""
        from civpulse_geo.spell.corrector import rebuild_dictionary

        mock_conn = self._make_mock_conn()
        mock_result = MagicMock()
        mock_result.rowcount = 42
        # The last execute call is the INSERT which returns rowcount
        mock_conn.execute.return_value = mock_result

        result = rebuild_dictionary(mock_conn)
        assert isinstance(result, int)


# ===================================================================
# load_spell_corrector tests
# ===================================================================

class TestLoadSpellCorrector:
    def test_creates_spell_corrector_from_db(self):
        """load_from_db() creates SpellCorrector from database rows."""
        from civpulse_geo.spell.corrector import load_spell_corrector, SpellCorrector

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("MERCER", 5),
            ("MARTIN", 10),
            ("KING", 8),
        ]
        mock_conn.execute.return_value = mock_result

        corrector = load_spell_corrector(mock_conn)

        assert isinstance(corrector, SpellCorrector)

    def test_create_dictionary_entry_called_for_each_word(self):
        """load_spell_corrector calls create_dictionary_entry for each DB row."""
        from civpulse_geo.spell.corrector import load_spell_corrector
        from symspellpy import SymSpell

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("MERCER", 5),
            ("MARTIN", 10),
        ]
        mock_conn.execute.return_value = mock_result

        with patch.object(SymSpell, "create_dictionary_entry") as mock_cde:
            load_spell_corrector(mock_conn)
            assert mock_cde.call_count == 2
            calls = [c[0] for c in mock_cde.call_args_list]
            words_loaded = [c[0] for c in calls]
            assert "MERCER" in words_loaded
            assert "MARTIN" in words_loaded


# ===================================================================
# Module-level import test
# ===================================================================

def test_spell_module_exports():
    """The spell package exports SpellCorrector, rebuild_dictionary, load_spell_corrector."""
    from civpulse_geo.spell import SpellCorrector, rebuild_dictionary, load_spell_corrector
    assert SpellCorrector is not None
    assert rebuild_dictionary is not None
    assert load_spell_corrector is not None
