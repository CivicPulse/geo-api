# Phase 18: Code Review - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 18-code-review
**Areas discussed:** Severity threshold, Review depth, Fix verification, Non-blocker tracking

---

## Severity Threshold

### Security Classification

| Option | Description | Selected |
|--------|-------------|----------|
| Any security issue blocks (Recommended) | Any unvalidated input, injection vector, or exposed secret is a blocker — even if exploitation requires internal network access | ✓ |
| Only exploitable issues block | Only findings with a realistic attack path block | |
| OWASP Top 10 blocks only | Use OWASP Top 10 as the bright line | |

**User's choice:** Any security issue blocks
**Notes:** Conservative stance — geo-api is internal-only but other CivPulse services trust its data

### Stability Classification

| Option | Description | Selected |
|--------|-------------|----------|
| Unhandled exceptions block (Recommended) | Any code path where an exception can bubble to the client as a 500 is a blocker | ✓ |
| Client-visible errors block | Both unhandled exceptions AND poor error messages are blockers | |
| Only crash-level issues block | Only findings that could crash the process or corrupt data block | |

**User's choice:** Unhandled exceptions block
**Notes:** Graceful degradation gaps are non-blockers

### Performance Classification

| Option | Description | Selected |
|--------|-------------|----------|
| N+1 queries and pool misconfig block (Recommended) | N+1 query patterns and connection pool sizing errors are blockers. Logic errors that cause wrong results also block. | ✓ |
| All measurable inefficiencies block | Anything that could be demonstrably faster blocks | |
| Only correctness issues block | Performance is a non-blocker category entirely | |

**User's choice:** N+1 queries and pool misconfig block
**Notes:** Suboptimal-but-correct code is a non-blocker

---

## Review Depth

### Codebase Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full codebase per team (Recommended) | Each team reviews all 45 source files through their lens | ✓ |
| Risk-prioritized focus | Security → API + providers, Stability → services + cascade, Performance → DB queries + dispatch | |
| Tiered approach | Full review of high-risk files, spot-check of lower-risk files | |

**User's choice:** Full codebase per team
**Notes:** ~8,300 LOC is manageable for agents

### Test Inclusion

| Option | Description | Selected |
|--------|-------------|----------|
| Review tests for correctness only (Recommended) | Check that existing 504 tests actually test what they claim. 29 test files. | ✓ |
| Include tests in full review | Review test files with same rigor as source code | |
| Exclude tests entirely | Review only the 45 source files | |

**User's choice:** Review tests for correctness only
**Notes:** None

---

## Fix Verification

### Verification Method

| Option | Description | Selected |
|--------|-------------|----------|
| Existing tests + ruff (Recommended) | Run full 504-test suite and ruff lint after each fix batch | |
| Existing tests + targeted new tests | Run full suite AND write a new test for each blocker fix | ✓ |
| Ruff + manual spot-check only | Run ruff for static analysis, manually verify each fix | |

**User's choice:** Existing tests + targeted new tests
**Notes:** More rigorous — write new tests for code paths not covered by existing suite

### Commit Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Batch by team (Recommended) | Each team's fixes go in one commit. 3 fix commits max. | ✓ |
| One commit per fix | Each individual blocker fix gets its own commit | |
| Single commit for all fixes | All blocker fixes from all three teams in one commit | |

**User's choice:** Batch by team
**Notes:** Cleaner git history, easier to review

---

## Non-Blocker Tracking

### Tracking Location

| Option | Description | Selected |
|--------|-------------|----------|
| Findings doc in .planning/ (Recommended) | Single 18-FINDINGS.md with all non-blockers categorized by team | ✓ |
| GitHub issues | Create a GitHub issue per non-blocker finding | |
| GSD todos | Add each non-blocker as a /gsd:add-todo item | ✓ |

**User's choice:** Both findings doc AND GSD todos
**Notes:** User specified: "create a detailed document of all findings, then add todos for each one but reference the document for details"

### Priority Tiers

| Option | Description | Selected |
|--------|-------------|----------|
| P1/P2/P3 priority tiers (Recommended) | P1: Fix before prod. P2: Fix when convenient. P3: Nice-to-have. | ✓ |
| Categorize by team only | Group by security/stability/performance, no priority ranking | |
| You decide | Claude picks the findings structure | |

**User's choice:** P1/P2/P3 priority tiers
**Notes:** Todos inherit the priority for sorting

---

## Claude's Discretion

- File partitioning and execution order across agent teams
- Findings report structure beyond team/priority framework
- Whether to group related findings or report individually

## Deferred Ideas

None — discussion stayed within phase scope
