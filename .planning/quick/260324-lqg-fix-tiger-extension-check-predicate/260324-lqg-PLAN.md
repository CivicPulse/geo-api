---
phase: quick
plan: 260324-lqg
type: execute
wave: 1
depends_on: []
files_modified:
  - src/civpulse_geo/providers/tiger.py
  - tests/test_tiger_provider.py
autonomous: true
requirements: [TIGR-04, TIGR-01, TIGR-02]
must_haves:
  truths:
    - "_tiger_extension_available returns False when postgis_tiger_geocoder is available in pg_available_extensions but NOT installed in the current database via CREATE EXTENSION"
    - "_tiger_extension_available returns True only when postgis_tiger_geocoder is actually installed (present in pg_extension)"
    - "Startup guard still returns False on any exception without crashing"
  artifacts:
    - path: "src/civpulse_geo/providers/tiger.py"
      provides: "Corrected CHECK_EXTENSION_SQL and updated docstrings"
      contains: "pg_extension"
    - path: "tests/test_tiger_provider.py"
      provides: "Updated test docstrings reflecting pg_extension"
  key_links:
    - from: "src/civpulse_geo/providers/tiger.py"
      to: "pg_extension catalog"
      via: "CHECK_EXTENSION_SQL"
      pattern: "SELECT 1 FROM pg_extension"
---

<objective>
Fix the Tiger extension availability check to query `pg_extension` (installed extensions) instead of `pg_available_extensions` (extensions available for installation). This prevents false-positive provider registration when the extension exists on the server but has not been activated with `CREATE EXTENSION` in the current database.

Purpose: Close TIGR-04 edge case where Tiger providers register but fail at runtime.
Output: Corrected SQL predicate, updated docstrings, updated tests.
</objective>

<execution_context>
@/home/kwhatcher/.claude/get-shit-done/workflows/execute-plan.md
@/home/kwhatcher/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/civpulse_geo/providers/tiger.py
@tests/test_tiger_provider.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix CHECK_EXTENSION_SQL and update docstrings/tests</name>
  <files>src/civpulse_geo/providers/tiger.py, tests/test_tiger_provider.py</files>
  <behavior>
    - Test: _tiger_extension_available returns True when pg_extension query finds a row (extension installed)
    - Test: _tiger_extension_available returns False when pg_extension query returns no row (extension not installed)
    - Test: _tiger_extension_available returns False on any exception (unchanged behavior)
  </behavior>
  <action>
1. In `src/civpulse_geo/providers/tiger.py`, change `CHECK_EXTENSION_SQL` (line 74-77) from:
   ```
   SELECT 1 FROM pg_available_extensions
   WHERE name = 'postgis_tiger_geocoder'
   ```
   to:
   ```
   SELECT 1 FROM pg_extension
   WHERE extname = 'postgis_tiger_geocoder'
   ```
   Note: `pg_extension` uses the column name `extname`, not `name`.

2. Update the module docstring (line 16) from "checks pg_available_extensions" to "checks pg_extension (installed extensions)".

3. Update the `_tiger_extension_available` function docstring (lines 85-95):
   - Change "Check whether the postgis_tiger_geocoder extension is available in PostgreSQL" to "Check whether the postgis_tiger_geocoder extension is installed in the current database"
   - Change "Queries pg_available_extensions (not pg_extension) so it reports availability even if the extension is not currently installed in this database." to "Queries pg_extension (installed extensions) so it only returns True when the extension has been activated with CREATE EXTENSION in the current database."
   - Update Returns line: "True if the extension is installed, False if absent or on any error."

4. In `tests/test_tiger_provider.py`, update the `TestTigerExtensionCheck` docstrings:
   - `test_returns_true_when_extension_present`: Change docstring to "Returns True when pg_extension query finds the row."
   - `test_returns_false_when_query_returns_none`: Change docstring to "Returns False when pg_extension query returns no row."
   - No logic changes needed in tests — they mock `session.execute()` return values which are independent of the actual SQL.
  </action>
  <verify>
    <automated>cd /home/kwhatcher/projects/civpulse/geo-api && uv run pytest tests/test_tiger_provider.py -x -q</automated>
  </verify>
  <done>CHECK_EXTENSION_SQL queries pg_extension.extname instead of pg_available_extensions.name. All three _tiger_extension_available tests pass. Docstrings in both tiger.py and test_tiger_provider.py reflect the corrected behavior.</done>
</task>

</tasks>

<verification>
1. `grep -n "pg_extension" src/civpulse_geo/providers/tiger.py` — shows pg_extension in CHECK_EXTENSION_SQL
2. `grep -n "pg_available_extensions" src/civpulse_geo/providers/tiger.py` — returns NO matches (old reference fully removed)
3. `uv run pytest tests/test_tiger_provider.py -x -q` — all tests pass
4. `uv run pytest tests/ -x -q` — full test suite passes (no regressions)
</verification>

<success_criteria>
- CHECK_EXTENSION_SQL queries `pg_extension WHERE extname = 'postgis_tiger_geocoder'`
- Zero references to `pg_available_extensions` remain in tiger.py
- All existing tests pass without logic changes
- Docstrings accurately describe the new behavior
</success_criteria>

<output>
After completion, create `.planning/quick/260324-lqg-fix-tiger-extension-check-predicate/260324-lqg-SUMMARY.md`
</output>
