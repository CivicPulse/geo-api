# Phase 21: CI/CD Pipeline - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Automate the build-test-deploy pipeline with GitHub Actions. PRs run CI (lint + test), merges to main build/scan/push a Docker image and deploy to dev via manifest-commit, and git tags trigger production promotion. Covers DEPLOY-06.

</domain>

<decisions>
## Implementation Decisions

### ArgoCD Dev Sync Strategy
- **D-01:** Manifest-commit strategy — CD workflow updates `k8s/overlays/dev/kustomization.yaml` with the new SHA tag (via `kustomize edit set image`) and commits+pushes. ArgoCD's existing `automated: prune + selfHeal` sync picks up the Git change and deploys. Full audit trail — every dev deployment is a Git commit.
- **D-02:** No ArgoCD Image Updater — no additional controller or RBAC setup needed. Pipeline stays in control of what gets deployed.

### Production Promotion
- **D-03:** Git tag release flow — creating a tag matching `v*` (e.g., `v1.3.0`) triggers the `promote-prod.yml` workflow. The workflow updates `k8s/overlays/prod/kustomization.yaml` with the SHA from the tagged commit and commits+pushes. ArgoCD prod syncs automatically.
- **D-04:** No GitHub environment protection rules needed — the git tag is the approval gate. Only maintainers with push access can create tags.

### Trivy Scan Policy
- **D-05:** Block on HIGH and CRITICAL severity — `exit-code: 1` with `severity: HIGH,CRITICAL`. Pipeline fails if any HIGH or CRITICAL CVEs are found.
- **D-06:** Include a `.trivyignore` file for known unfixable base image vulnerabilities (e.g., OpenSSL, glibc issues in python:3.12-slim-bookworm that have no upstream patch yet). Each entry must have a comment explaining why it's ignored.

### Workflow Structure
- **D-07:** Three separate workflow files with single responsibility each:
  - `ci.yml` — triggered on `pull_request` to main. Runs `ruff` lint + full `pytest` suite. Must pass before merge.
  - `cd.yml` — triggered on `push` to main. Builds Docker image, runs Trivy scan, pushes to GHCR with SHA tag, updates dev kustomization and commits.
  - `promote-prod.yml` — triggered on `push` of `v*` tags. Updates prod kustomization and commits.
- **D-08:** Separate files enable least-privilege permissions — only `cd.yml` needs GHCR write + repo write. `ci.yml` needs only read.

### Supply Chain Security
- **D-09:** ALL GitHub Actions must be pinned to full commit SHAs, not mutable tags. This is a hard requirement based on the Trivy supply chain compromise (March 2026). Applies to: `actions/checkout`, `docker/build-push-action`, `docker/login-action`, `aquasecurity/trivy-action`, and any other third-party actions used.
- **D-10:** Reference: https://www.microsoft.com/en-us/security/blog/2026/03/24/detecting-investigating-defending-against-trivy-supply-chain-compromise/

### Claude's Discretion
- Exact commit SHAs for each pinned action (look up current latest stable)
- `uv` caching strategy in CI (cache key based on uv.lock hash)
- Whether cd.yml needs concurrency guards to prevent parallel deploy commits
- Git author/committer identity for automated deploy commits (github-actions bot or dedicated bot account)
- Whether to add SARIF upload for Trivy results (GitHub Security tab integration)
- Branch protection rule configuration (require CI to pass before merge)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — DEPLOY-06 acceptance criteria
- `.planning/ROADMAP.md` section "Phase 21" — Success criteria (3 items: PR CI gate, merge CD pipeline, manual prod promotion)

### Prior Phase Context
- `.planning/phases/19-dockerfile-and-database-provisioning/19-CONTEXT.md` — D-08 (GHCR repo), D-09 (SHA tag strategy), D-10 (manual build in Phase 19, Phase 21 automates), D-11 (public image, no imagePullSecret)
- `.planning/phases/20-health-resilience-and-k8s-manifests/20-CONTEXT.md` — D-04 (Kustomize base+overlays), D-05 (ArgoCD automated sync), D-06 (Secrets excluded from Kustomize)

### Existing Files (primary targets)
- `Dockerfile` — Multi-stage production image with `ARG GIT_COMMIT=unknown` for build-time injection
- `k8s/overlays/dev/kustomization.yaml` — Dev overlay (CD workflow will update image tag here)
- `k8s/overlays/prod/kustomization.yaml` — Prod overlay (promote workflow will update image tag here)
- `k8s/overlays/dev/argocd-app.yaml` — ArgoCD dev Application CR (watches `k8s/overlays/dev` path)
- `k8s/overlays/prod/argocd-app.yaml` — ArgoCD prod Application CR (watches `k8s/overlays/prod` path)
- `pyproject.toml` — Project config with pytest settings (asyncio_mode, testpaths)

### Security Reference
- Microsoft Security Blog: Trivy supply chain compromise (2026-03-24) — Pin all actions to commit SHAs
  URL: https://www.microsoft.com/en-us/security/blog/2026/03/24/detecting-investigating-defending-against-trivy-supply-chain-compromise/

### Infrastructure Reference
- GHCR: `ghcr.io/civicpulse/geo-api` (public, no imagePullSecret needed)
- ArgoCD: `automated: prune + selfHeal` on both dev and prod Application CRs
- K8s namespaces: `civpulse-dev` and `civpulse-prod`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Dockerfile` — Already multi-stage with `ARG GIT_COMMIT`. CD workflow passes `--build-arg GIT_COMMIT=$SHA` at build time.
- `k8s/overlays/*/kustomization.yaml` — Both already have an `images:` section with `newTag: latest`. CD/promote workflows update this with `kustomize edit set image`.
- `pyproject.toml` — pytest configured with `asyncio_mode = "auto"` and `testpaths = ["tests"]`. CI workflow runs `uv run pytest`.

### Established Patterns
- **Kustomize image override**: Both overlays use `images:` stanza to set the tag. `kustomize edit set image` is the idempotent way to update it.
- **ArgoCD auto-sync**: Both Application CRs have `automated: prune + selfHeal`. Any Git change to the overlay path triggers deployment within ArgoCD's sync interval.
- **No `.github/` directory exists yet** — all three workflow files are net-new.

### Integration Points
- CD workflow commits to `k8s/overlays/dev/kustomization.yaml` on main — this commit itself must NOT re-trigger the CD workflow (infinite loop). Use `[skip ci]` in commit message or filter by changed paths.
- Promote workflow commits to `k8s/overlays/prod/kustomization.yaml` — same loop prevention needed.
- GHCR login uses `GITHUB_TOKEN` (automatic in Actions) for public repos.

</code_context>

<specifics>
## Specific Ideas

- The Trivy supply chain compromise (March 2026) makes SHA-pinning non-negotiable. Every `uses:` line must reference a full 40-character commit hash with a comment noting the version it corresponds to (e.g., `actions/checkout@abc123 # v4.2.0`).
- `.trivyignore` entries must include comments explaining why each CVE is ignored and when to revisit.
- The CD workflow's deploy commit must not re-trigger the CD pipeline — implement loop prevention via `[skip ci]` in commit messages or path-based filtering.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-ci-cd-pipeline*
*Context gathered: 2026-03-30*
