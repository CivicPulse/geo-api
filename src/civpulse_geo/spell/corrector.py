"""SpellCorrector subsystem for offline street name typo recovery.

Uses symspellpy (SymSpell algorithm) with a PostgreSQL-backed dictionary
populated from staging tables (openaddresses_points, nad_points,
macon_bibb_points).

Key design decisions (from Phase 13 RESEARCH.md):
- D-01: max_edit_distance=2 — catches single and double typos
- D-02: Multi-word street names corrected per-word independently
- D-03: Verbosity.TOP — return only the top candidate per token
- D-04: Skip tokens < 4 characters (short names like "Oak", "Elm" have
        too many edit-distance neighbors; pass through uncorrected)
- D-08: spell_dictionary table is the centralized source of truth
- D-09: Loaded at API worker startup (one query → in-memory for all requests)
- D-10: Auto-rebuilt after every CLI data-load command
"""
from __future__ import annotations

from symspellpy import SymSpell, Verbosity
from sqlalchemy import text


class SpellCorrector:
    """Corrects street name typos using the SymSpell symmetric delete algorithm.

    Operates on individual word tokens (D-02): split on spaces, correct each
    token independently, rejoin. Short tokens (< 4 chars) are passed through
    unchanged (D-04) to avoid over-correcting short names like "Oak" or "Elm".
    """

    def __init__(self, sym_spell: SymSpell) -> None:
        self._sym_spell = sym_spell

    def correct_street_name(self, street_name: str) -> str:
        """Return street_name with each word token spell-corrected.

        Args:
            street_name: The street name token to correct (e.g., "MRCCER AVE").

        Returns:
            The spell-corrected street name. Empty/falsy input is returned as-is.
        """
        if not street_name:
            return street_name

        tokens = street_name.split()
        corrected = []
        for token in tokens:
            if len(token) < 4:  # D-04: skip short tokens
                corrected.append(token)
                continue
            suggestions = self._sym_spell.lookup(
                token.upper(), Verbosity.TOP, max_edit_distance=2  # D-01, D-03
            )
            corrected.append(suggestions[0].term if suggestions else token.upper())
        return " ".join(corrected)


def rebuild_dictionary(conn) -> int:
    """Rebuild the spell_dictionary table from all staging tables.

    Extracts individual word tokens from street_name columns in
    openaddresses_points, nad_points, and macon_bibb_points using
    PostgreSQL's unnest(string_to_array()) for proper word tokenization.
    Tiger featnames are included when available (SPELL-02).

    Uses TRUNCATE + INSERT with ON CONFLICT for idempotent rebuild (D-10).

    Args:
        conn: A synchronous SQLAlchemy connection with autocommit disabled.

    Returns:
        Number of words inserted/updated in spell_dictionary.
    """
    conn.execute(text("TRUNCATE spell_dictionary"))

    result = conn.execute(
        text(
            """
            INSERT INTO spell_dictionary (word, frequency)
            SELECT word, SUM(cnt)::integer AS frequency
            FROM (
                SELECT
                    unnest(string_to_array(upper(street_name), ' ')) AS word,
                    1 AS cnt
                FROM openaddresses_points
                WHERE street_name IS NOT NULL
                UNION ALL
                SELECT
                    unnest(string_to_array(upper(street_name), ' ')) AS word,
                    1 AS cnt
                FROM nad_points
                WHERE street_name IS NOT NULL
                UNION ALL
                SELECT
                    unnest(string_to_array(upper(street_name), ' ')) AS word,
                    1 AS cnt
                FROM macon_bibb_points
                WHERE street_name IS NOT NULL
            ) all_words
            WHERE length(word) >= 2
            GROUP BY word
            ON CONFLICT (word) DO UPDATE SET
                frequency = EXCLUDED.frequency,
                updated_at = now()
            """
        )
    )

    # Include Tiger featnames when available (SPELL-02: "supplemented with
    # Tiger featnames where available")
    try:
        conn.execute(
            text(
                """
                INSERT INTO spell_dictionary (word, frequency)
                SELECT word, SUM(cnt)::integer AS frequency
                FROM (
                    SELECT
                        unnest(string_to_array(upper(name), ' ')) AS word,
                        1 AS cnt
                    FROM tiger.featnames
                    WHERE name IS NOT NULL
                ) tiger_words
                WHERE length(word) >= 2
                GROUP BY word
                ON CONFLICT (word) DO UPDATE SET
                    frequency = EXCLUDED.frequency + EXCLUDED.frequency,
                    updated_at = now()
                """
            )
        )
    except Exception:
        # Tiger featnames table may not exist; silently skip (provider is optional)
        pass

    conn.commit()
    return result.rowcount


def load_spell_corrector(conn) -> SpellCorrector:
    """Load all words from spell_dictionary into an in-memory SymSpell object.

    This is called once at API worker startup (D-09). The SymSpell object is
    stored in app.state.spell_corrector for use across all requests.

    Args:
        conn: A synchronous SQLAlchemy connection.

    Returns:
        A SpellCorrector instance loaded with all dictionary words.
    """
    sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    rows = conn.execute(
        text("SELECT word, frequency FROM spell_dictionary")
    ).fetchall()
    for word, freq in rows:
        sym_spell.create_dictionary_entry(word, freq)
    return SpellCorrector(sym_spell)
