"""Spell correction subsystem for CivPulse Geo API.

Provides offline street name typo recovery using symspellpy (SymSpell algorithm)
backed by a PostgreSQL spell_dictionary table populated from staging tables.

Public API:
    SpellCorrector  — corrects street name tokens using in-memory SymSpell
    rebuild_dictionary — rebuilds spell_dictionary table from staging tables
    load_spell_corrector — loads spell_dictionary from DB into SpellCorrector
"""
from civpulse_geo.spell.corrector import SpellCorrector, rebuild_dictionary, load_spell_corrector

__all__ = ["SpellCorrector", "rebuild_dictionary", "load_spell_corrector"]
