# Phase 21: CI/CD Pipeline - Research

**Researched:** 2026-03-30
**Domain:** GitHub Actions CI/CD — Python/Docker/GHCR/Kustomize/ArgoCD
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Manifest-commit strategy — CD workflow updates `k8s/overlays/dev/kustomization.yaml` with the new SHA tag (via `kustomize edit set image`) and commits+pushes. ArgoCD's existing `automated: prune + selfHeal` sync picks up the Git change and deploys.
- **D-02:** No ArgoCD Image Updater — no additional controller or RBAC setup needed.
- **D-03:** Git tag release flow — creating a tag matching `v*` triggers `promote-prod.yml`. The workflow updates `k8s/overlays/prod/kustomization.yaml` with the SHA from the tagged commit and commits+pushes.
- **D-04:** No GitHub environment protection rules needed — the git tag is the approval gate.
- **D-05:** Block on HIGH and CRITICAL severity — `exit-code: 1` with `severity: HIGH,CRITICAL`.
- **D-06:** Include a `.trivyignore` file for known unfixable base image vulnerabilities. Each entry must have a comment explaining why it's ignored.
- **D-07:** Three separate workflow files: `ci.yml` (PR), `cd.yml` (push to main), `promote-prod.yml` (v* tag).
- **D-08:** Separate files enable least-privilege permissions — only `cd.yml` needs GHCR write + repo write. `ci.yml` needs only read.
- **D-09:** ALL GitHub Actions must be pinned to full commit SHAs, not mutable tags. Hard requirement based on Trivy supply chain compromise (March 2026).
- **D-10:** Reference: https://www.microsoft.com/en-us/security/blog/2026/03/24/detecting-investigating-defending-against-trivy-supply-chain-compromise/

### Claude's Discretion

- Exact commit SHAs for each pinned action (look up current latest stable)
- `uv` caching strategy in CI (cache key based on uv.lock hash)
- Whether cd.yml needs concurrency guards to prevent parallel deploy commits
- Git author/committer identity for automated deploy commits (github-actions bot or dedicated bot account)
- Whether to add SARIF upload for Trivy results (GitHub Security tab integration)
- Branch protection rule configuration (require CI to pass before merge)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-06 | GitHub Actions workflow (build → GHCR push with sha-tag → manifest update) | Covered by Standard Stack (actions SHAs, kustomize strategy, GHCR), Architecture Patterns (workflow structure), and Code Examples (all three workflow files) |
</phase_requirements>

---

## Summary

This phase creates three GitHub Actions workflow files from scratch — no `.github/` directory exists yet. The stack is entirely standard for Python/Docker/ArgoCD GitOps: `astral-sh/setup-uv` for Python environment, `docker/build-push-action` for image builds, `aquasecurity/trivy-action` for vulnerability scanning, and a `kustomize edit set image` + git commit pattern for manifest-based ArgoCD deployment.

The critical security requirement (D-09) — SHA-pinning all actions — has been fully resolved by direct GitHub API queries. All exact commit SHAs for the latest stable versions of every required action are documented below, verified against the GitHub releases API on 2026-03-30. The Trivy supply chain compromise (March 2026) makes these SHAs non-negotiable.

The test suite (548 passing, 2 skipped, 2 warnings) runs entirely with mocked database and HTTP dependencies — no real PostgreSQL or network services are required for `uv run pytest`. Fiona 1.10.x bundles its own GDAL shared libraries (`fiona.libs/`), so no `apt-get install libgdal-dev` is needed in the CI runner. The CI workflow is safe to run on a standard `ubuntu-latest` runner without any system library setup.

**Primary recommendation:** Use `astral-sh/ruff-action` (SHA-pinned) for lint, `astral-sh/setup-uv` + `uv run pytest` for tests in `ci.yml`, and `[skip ci]` in the automated manifest-commit message to prevent the infinite loop in `cd.yml` and `promote-prod.yml`.

---

## Standard Stack

### Core

| Library/Action | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| `actions/checkout` | v6.0.2 | Checkout repo in all workflows | Official GitHub action, required for all workflows |
| `astral-sh/setup-uv` | v8.0.0 | Install uv + Python 3.12, manage venv cache | Official uv action; `enable-cache: true` caches the uv download cache keyed on `uv.lock` |
| `astral-sh/ruff-action` | v3.6.1 | Run `ruff check` in CI | Official ruff action; installs pinned ruff binary, no dev dep needed |
| `docker/login-action` | v4.0.0 | Authenticate to GHCR | Official Docker action; supports `registry: ghcr.io` with `GITHUB_TOKEN` |
| `docker/metadata-action` | v6.0.0 | Generate Docker tags + labels | Official Docker action; generates OCI labels and `sha-` prefixed tags |
| `docker/build-push-action` | v7.0.0 | Build multi-platform image + push to GHCR | Official Docker action; supports `--build-arg`, cache-from/to |
| `aquasecurity/trivy-action` | v0.35.0 | Vulnerability scan of built image | Official Trivy action; supports `exit-code: 1`, SARIF output, `.trivyignore` |
| `github/codeql-action/upload-sarif` | v3 | Upload Trivy SARIF to GitHub Security tab | Official CodeQL action; public repos get Security tab for free |

### Verified Action Commit SHAs (2026-03-30)

**All `uses:` lines in workflow files MUST use these exact SHAs.**

| Action | Version | Commit SHA | Usage |
|--------|---------|------------|-------|
| `actions/checkout` | v6.0.2 | `de0fac2e4500dabe0009e67214ff5f5447ce83dd` | All 3 workflows |
| `astral-sh/setup-uv` | v8.0.0 | `cec208311dfd045dd5311c1add060b2062131d57` | `ci.yml` |
| `astral-sh/ruff-action` | v3.6.1 | `4919ec5cf1f49eff0871dbcea0da843445b837e6` | `ci.yml` |
| `docker/login-action` | v4.0.0 | `b45d80f862d83dbcd57f89517bcf500b2ab88fb2` | `cd.yml` |
| `docker/metadata-action` | v6.0.0 | `030e881283bb7a6894de51c315a6bfe6a94e05cf` | `cd.yml` |
| `docker/build-push-action` | v7.0.0 | `d08e5c354a6adb9ed34480a06d141179aa583294` | `cd.yml` |
| `aquasecurity/trivy-action` | v0.35.0 | `57a97c7e7821a5776cebc9bb87c984fa69cba8f1` | `cd.yml` |
| `github/codeql-action/upload-sarif` | v3 | `5c8a8a642e79153f5d047b10ec1cba1d1cc65699` | `cd.yml` (SARIF) |

**Source:** GitHub Releases API queried 2026-03-30. Confidence: HIGH.

### Kustomize Installation

No kustomize GitHub Action is sufficiently maintained for SHA-pinning. Use direct binary download instead:

```bash
curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize/v5.8.1/kustomize_v5.8.1_linux_amd64.tar.gz" | tar xz
sudo mv kustomize /usr/local/bin/kustomize
```

Latest version: `kustomize/v5.8.1` (verified 2026-03-30).

### Installation (dev environment only — not needed in CI)

```bash
# ruff is a uv tool, not a project dev dep
# For CI, astral-sh/ruff-action handles installation
uv tool install ruff
```

---

## Architecture Patterns

### Recommended Project Structure

```
.github/
├── workflows/
│   ├── ci.yml              # PR gate: ruff lint + pytest
│   ├── cd.yml              # main merge: build → scan → push → dev manifest update
│   └── promote-prod.yml    # v* tag: prod manifest update
.trivyignore                # Known-unfixable CVE suppressions with comments
```

### Pattern 1: `ci.yml` — Pull Request Gate

**What:** Runs on every PR targeting `main`. Runs `ruff check` and `uv run pytest`. Must pass before merge.
**When to use:** Always triggered on `pull_request` to `main`.

```yaml
# Source: GitHub Actions documentation + astral-sh/setup-uv README
name: CI

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - name: Lint with ruff
        uses: astral-sh/ruff-action@4919ec5cf1f49eff0871dbcea0da843445b837e6 # v3.6.1
        with:
          src: "src"

      - name: Set up uv and Python 3.12
        uses: astral-sh/setup-uv@cec208311dfd045dd5311c1add060b2062131d57 # v8.0.0
        with:
          python-version: "3.12"
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Install dependencies
        run: uv sync --locked --frozen

      - name: Run test suite
        run: uv run pytest
```

**Key points:**
- `permissions: contents: read` — minimal permissions per D-08
- `enable-cache: true` on `setup-uv` caches the uv download cache (not the venv) keyed by `uv.lock`
- `uv sync --locked --frozen` installs dev deps including `pytest` and `pytest-asyncio`
- `uv run pytest` uses `testpaths = ["tests"]` from `pyproject.toml` — no path argument needed
- No database or external services required — all tests use mocked dependencies (confirmed: 548 tests, all mock-based)
- Fiona 1.10.x bundles its own GDAL in `fiona.libs/` — no `apt-get install libgdal-dev` needed

### Pattern 2: `cd.yml` — Merge-to-Main Deployment

**What:** Triggered on push to `main`. Builds Docker image, scans with Trivy, pushes to GHCR with SHA tag, updates dev kustomization and commits.
**When to use:** Every merge to `main`.

```yaml
# Source: docker/build-push-action README + aquasecurity/trivy-action README
name: CD

on:
  push:
    branches: [main]
    paths-ignore:
      - 'k8s/overlays/**'   # Prevent loop: manifest commits must not re-trigger

permissions:
  contents: write        # Required: push manifest commit back to repo
  packages: write        # Required: push to GHCR
  security-events: write # Required: upload SARIF to Security tab

concurrency:
  group: cd-deploy
  cancel-in-progress: false  # Never cancel an in-progress deploy

jobs:
  build-scan-push:
    runs-on: ubuntu-latest
    outputs:
      sha_tag: ${{ steps.meta.outputs.version }}
      image: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - name: Login to GHCR
        uses: docker/login-action@b45d80f862d83dbcd57f89517bcf500b2ab88fb2 # v4.0.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@030e881283bb7a6894de51c315a6bfe6a94e05cf # v6.0.0
        with:
          images: ghcr.io/civicpulse/geo-api
          tags: |
            type=sha,prefix=sha-,format=short

      - name: Build and push
        id: build
        uses: docker/build-push-action@d08e5c354a6adb9ed34480a06d141179aa583294 # v7.0.0
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            GIT_COMMIT=${{ github.sha }}

      - name: Trivy vulnerability scan
        uses: aquasecurity/trivy-action@57a97c7e7821a5776cebc9bb87c984fa69cba8f1 # v0.35.0
        with:
          image-ref: ${{ steps.meta.outputs.tags }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          exit-code: '1'
          severity: 'HIGH,CRITICAL'
          trivyignores: '.trivyignore'

      - name: Upload Trivy SARIF to Security tab
        if: always()
        uses: github/codeql-action/upload-sarif@5c8a8a642e79153f5d047b10ec1cba1d1cc65699 # v3
        with:
          sarif_file: 'trivy-results.sarif'

  update-dev-manifest:
    runs-on: ubuntu-latest
    needs: build-scan-push
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Install kustomize
        run: |
          curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize/v5.8.1/kustomize_v5.8.1_linux_amd64.tar.gz" | tar xz
          sudo mv kustomize /usr/local/bin/kustomize

      - name: Update dev image tag
        run: |
          cd k8s/overlays/dev
          kustomize edit set image ghcr.io/civicpulse/geo-api=${{ needs.build-scan-push.outputs.sha_tag }}

      - name: Commit and push manifest
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add k8s/overlays/dev/kustomization.yaml
          git commit -m "chore(deploy): update dev image to ${{ needs.build-scan-push.outputs.sha_tag }} [skip ci]"
          git push
```

**Key loop prevention note:** `paths-ignore: ['k8s/overlays/**']` prevents the manifest commit from re-triggering `cd.yml`. The `[skip ci]` in the commit message is a secondary safety guard. Both together are belt-and-suspenders.

**Concurrency:** `cancel-in-progress: false` — a deploy in progress should never be cancelled by a subsequent push. Use a single-group mutex instead.

### Pattern 3: `promote-prod.yml` — Production Promotion

**What:** Triggered on push of `v*` tags. Updates prod kustomization with the SHA from the tagged commit.
**When to use:** Manual — maintainer creates a `v1.x.y` tag.

```yaml
# Source: GitHub Actions documentation
name: Promote to Production

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  update-prod-manifest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          ref: main  # Always update manifests on main branch, not detached HEAD

      - name: Install kustomize
        run: |
          curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize/v5.8.1/kustomize_v5.8.1_linux_amd64.tar.gz" | tar xz
          sudo mv kustomize /usr/local/bin/kustomize

      - name: Derive SHA from tag
        id: tag_sha
        run: echo "sha=sha-$(git rev-parse --short ${{ github.sha }})" >> $GITHUB_OUTPUT

      - name: Update prod image tag
        run: |
          cd k8s/overlays/prod
          kustomize edit set image ghcr.io/civicpulse/geo-api=${{ steps.tag_sha.outputs.sha }}

      - name: Commit and push manifest
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add k8s/overlays/prod/kustomization.yaml
          git commit -m "chore(deploy): promote prod to ${{ steps.tag_sha.outputs.sha }} (${{ github.ref_name }}) [skip ci]"
          git push origin main
```

**Critical:** `actions/checkout` with a `v*` tag trigger checks out the tag's commit in detached HEAD state. The `ref: main` input forces checkout of `main` so the manifest commit lands on the correct branch.

### Pattern 4: `.trivyignore` Format

**What:** Suppresses known-unfixable CVEs in the base image (`python:3.12-slim-bookworm`).

```
# CVE-XXXX-XXXXX: OpenSSL vulnerability in python:3.12-slim-bookworm base image.
# Upstream Debian bookworm patch not yet available as of 2026-03-30.
# No fix version exists — revisit when debian security tracker shows a fix.
# References: https://security.debian.org/tracker/XXXXXX
CVE-XXXX-XXXXX
```

**Confidence:** HIGH for format. LOW for specific CVE IDs — those must be discovered by running Trivy against the actual image before checking in `.trivyignore`.

### Anti-Patterns to Avoid

- **Mutable tag pinning (`uses: actions/checkout@v4`):** Mutable tags can be moved to malicious commits (Trivy supply chain compromise, March 2026). Always use full 40-char SHA.
- **`actions/setup-python` + `pip install`:** Redundant when `astral-sh/setup-uv` handles both Python installation and dep management. Setup-uv is faster and handles the lock file directly.
- **`git push --force` in manifest commits:** The manifest-commit strategy relies on fast-forward merges to `main`. Force push would corrupt history.
- **`cancel-in-progress: true` on CD concurrency:** Cancelling an in-flight deployment leaves the cluster in an unknown intermediate state.
- **`kustomize edit set image` without `cd`ing into the overlay directory:** `kustomize edit` modifies the `kustomization.yaml` in the current working directory. Must `cd k8s/overlays/{env}` first.
- **Using `github.sha` directly as the image tag:** GitHub SHA is 40 chars; GHCR allows it but `docker/metadata-action` with `type=sha,format=short` gives the 7-char `sha-abc1234` format that matches Phase 19's existing tag convention.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker image building + GHCR login | Shell script with `docker build && docker push` | `docker/login-action` + `docker/build-push-action` | Build cache, multi-platform support, OCI labels, provenance attestations |
| Image vulnerability scanning | Custom scripts | `aquasecurity/trivy-action` | DB update management, SARIF output format, exit code control, trivyignore support |
| OCI image tagging | Manual `docker tag` | `docker/metadata-action` | Consistent tag format, OCI labels (org.opencontainers.image.*), git SHA extraction |
| uv environment in CI | `curl -LsSf ... | sh && uv sync` | `astral-sh/setup-uv` | Caching, Python version management, lockfile-aware cache keys |
| Ruff linting | `pip install ruff && ruff check` | `astral-sh/ruff-action` | Pinned ruff binary, no dev dep needed, official action |

**Key insight:** The Docker action ecosystem (`docker/*`) handles OCI image building complexity (layer caching, multi-arch, provenance). The astral-sh actions (`setup-uv`, `ruff-action`) are the official channel for uv/ruff and handle version management better than manual installs.

---

## Common Pitfalls

### Pitfall 1: CD Workflow Infinite Loop
**What goes wrong:** `cd.yml` triggers on push to `main`. Its final step commits `kustomization.yaml` back to `main`. This push triggers another `cd.yml` run. Infinite loop.
**Why it happens:** The manifest-commit strategy creates a write-back to the same branch that triggers the workflow.
**How to avoid:** Add `paths-ignore: ['k8s/overlays/**']` to the `on: push:` trigger. This ensures pushes that only modify `k8s/overlays/**` (i.e., manifest commits) do not re-trigger the workflow. Also include `[skip ci]` in the commit message as a belt-and-suspenders guard.
**Warning signs:** Exponentially growing Actions run count in the GitHub Actions tab.

### Pitfall 2: Tag Checkout in Detached HEAD
**What goes wrong:** `promote-prod.yml` triggers on `v*` tag push. `actions/checkout` checks out the tagged commit in detached HEAD mode. `git push origin main` at the end fails — HEAD is not on `main`.
**Why it happens:** Git tag triggers check out the SHA the tag points to, not a branch.
**How to avoid:** Pass `ref: main` to `actions/checkout` so the working tree is on `main`. The tag still provides the commit SHA via `${{ github.sha }}` which is the SHA the tag points to.
**Warning signs:** `git push` error "The current branch HEAD has no upstream branch."

### Pitfall 3: GITHUB_TOKEN Scope for Repo Write
**What goes wrong:** Manifest-commit step fails with "Permission to CivicPulse/geo-api.git denied to github-actions[bot]."
**Why it happens:** Default workflow `GITHUB_TOKEN` permissions in organization repos may restrict write access. The `contents: write` permission must be explicitly granted.
**How to avoid:** Set `permissions: contents: write` at the job level in `cd.yml` and `promote-prod.yml`. Verify by checking the repo's Actions > General > Workflow permissions setting.
**Warning signs:** Push step fails with HTTP 403.

### Pitfall 4: Trivy Scan Fails Before Image Push
**What goes wrong:** Trivy scans a local image that was not pushed to GHCR. If the scan fails (HIGH/CRITICAL CVE), the image should not be pushed — but it may have been pushed already.
**Why it happens:** Workflow step order: build → push → scan means the image is public before it's scanned.
**How to avoid:** Build the image, scan it as a local tar or via `docker.io/` reference before pushing to GHCR. Alternatively, accept that the image is pushed and treat the scan as a gate for the *manifest commit* (not the push). Decision: the scan in `cd.yml` runs after push — the manifest commit only happens if scan passes. Unpushed images are not deployed.
**Warning signs:** A HIGH/CRITICAL CVE image tag exists in GHCR but dev was not deployed (good — manifest commit was blocked).

### Pitfall 5: ruff Configuration Absent
**What goes wrong:** `ruff check src/` in CI fails on code that was passing locally.
**Why it happens:** ruff is installed as a `uv tool` globally (not as a project dev dep). Running `ruff check` with no config in `pyproject.toml` uses ruff defaults. The `astral-sh/ruff-action` also uses ruff defaults. Both should be consistent — but there is currently no `[tool.ruff]` section in `pyproject.toml`.
**How to avoid:** Add a minimal `[tool.ruff]` section to `pyproject.toml` (at minimum `target-version = "py312"`) so CI and local runs behave identically. Do NOT add ruff as a project dev dep — the action handles installation.
**Warning signs:** CI ruff failure on code that `ruff check` passes locally with a different ruff version.

### Pitfall 6: `kustomize edit set image` in Wrong Directory
**What goes wrong:** `kustomize edit set image ghcr.io/civicpulse/geo-api=sha-abc1234` runs in repo root. It looks for a `kustomization.yaml` in the current directory, finds none, errors.
**Why it happens:** `kustomize edit` modifies the nearest `kustomization.yaml` in the current directory.
**How to avoid:** Always `cd k8s/overlays/{env}` before running `kustomize edit set image`.
**Warning signs:** `Error: unable to find a kustomization file in the current directory.`

---

## Code Examples

### `.trivyignore` Format (with required comments)

```
# CVE-XXXX-YYYYY: [Vulnerability name] in [package] [version]
# Base image: python:3.12-slim-bookworm
# Status: No fix available in Debian bookworm as of YYYY-MM-DD
# Source: https://security.debian.org/tracker/CVE-XXXX-YYYYY
# Revisit: Check debian security tracker for fix availability monthly
CVE-XXXX-YYYYY
```

**Note:** The actual CVE IDs in `.trivyignore` must be discovered by running Trivy against the built image. The file cannot be pre-populated before the first workflow run. Wave 0 task: run `trivy image --severity HIGH,CRITICAL ghcr.io/civicpulse/geo-api:sha-42d5282` locally to identify which CVEs need suppression.

### Extracting Short SHA from git context

```yaml
# Inside promote-prod.yml — derive sha- tag from the commit the tag points to
- name: Derive SHA tag
  id: tag_sha
  run: echo "sha=sha-$(git rev-parse --short ${{ github.sha }})" >> $GITHUB_OUTPUT

# Then use:
kustomize edit set image ghcr.io/civicpulse/geo-api=${{ steps.tag_sha.outputs.sha }}
```

### Branch Protection Rule via gh CLI

```bash
# Enable branch protection requiring ci workflow to pass before merge
gh api repos/CivicPulse/geo-api/branches/main/protection \
  --method PUT \
  --header "Accept: application/vnd.github+json" \
  -f required_status_checks='{"strict":true,"contexts":["lint-and-test"]}' \
  -f enforce_admins=false \
  -f required_pull_request_reviews=null \
  -f restrictions=null
```

**Note:** The `contexts` value must match the job name in `ci.yml`. The job name `lint-and-test` (or whatever is used) must match exactly. Confidence: MEDIUM — GitHub free org plan supports required status checks on public repos.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `actions/setup-python` + `pip install` | `astral-sh/setup-uv` | 2024+ | Faster CI, lock-file-aware caching, single action for Python + deps |
| `actions/checkout@v4` (mutable tag) | `actions/checkout@<full-sha>` | March 2026 (Trivy supply chain compromise) | Security requirement — mutable tags are a supply chain attack vector |
| ArgoCD Image Updater | Manifest-commit strategy (kustomize edit + git push) | Project decision (D-01) | Full audit trail, no additional controller, pipeline controls deployment |
| Floating `latest` tag | Immutable `sha-<short>` tag | Phase 19 D-09 | Reproducible deploys, full commit traceability |

**Deprecated/outdated:**
- `mutable action tags` (e.g., `@v4`, `@main`): Deprecated as a security practice post-March 2026 Trivy supply chain incident.
- `actions/setup-python` alone for Python CI: Superseded by `astral-sh/setup-uv` which handles Python installation + lockfile-aware dep caching in a single step.

---

## Open Questions

1. **Specific CVE IDs for `.trivyignore`**
   - What we know: `python:3.12-slim-bookworm` has known unfixable CVEs (OpenSSL, glibc). Per D-06, these must be listed in `.trivyignore` with comments.
   - What's unclear: Exact CVE IDs and whether they are still present in the current image pull (images update daily).
   - Recommendation: Wave 0 task in `cd.yml` plan — run `docker pull python:3.12-slim-bookworm && trivy image --severity HIGH,CRITICAL python:3.12-slim-bookworm` locally to identify which CVEs need suppression before implementing `.trivyignore`.

2. **ruff configuration scope**
   - What we know: No `[tool.ruff]` section exists in `pyproject.toml`. ruff defaults apply.
   - What's unclear: Whether the current codebase passes `ruff check src/` under defaults. Locally, ruff 0.12.7 is installed as a tool; the action installs latest by default.
   - Recommendation: Add `[tool.ruff] target-version = "py312"` to `pyproject.toml` as Wave 0 task, and run `ruff check src/` locally to verify zero failures before implementing `ci.yml`.

3. **Trivy scan timing relative to push**
   - What we know: D-05 requires blocking on HIGH/CRITICAL. The image is pushed before scan in the standard pattern.
   - What's unclear: Whether a push-then-scan sequence is acceptable (an unfixable CVE image exists in GHCR temporarily).
   - Recommendation: Accept push-then-scan since the manifest commit is the deploy gate. The GHCR image exists but ArgoCD only deploys what the manifest references. This is the standard Trivy + GitOps pattern.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | cd.yml image build (local dev reference) | Yes | 29.3.1 | — |
| uv | ci.yml Python/deps | Yes | 0.8.14 | — |
| gh CLI | Branch protection setup, SHA lookups | Yes | 2.89.0 | GitHub web UI |
| kustomize | cd.yml / promote-prod.yml | No (local) | — | Installed in workflow via curl download |
| Python 3.12 | ci.yml pytest | Provided by setup-uv in Actions | — | — |
| GHCR (`ghcr.io/civicpulse/geo-api`) | cd.yml image push | Yes (public, pre-existing) | sha-42d5282 published | — |

**Missing dependencies with no fallback:** None. Kustomize is not installed locally but is downloaded in the workflow itself.

**Note:** All three workflow files run on GitHub-hosted `ubuntu-latest` runners. No self-hosted runner dependencies.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DEPLOY-06 | PR CI workflow triggers on pull_request to main | manual-only | N/A — verify in GitHub Actions tab after merge | N/A |
| DEPLOY-06 | CI passes: ruff check + pytest green | manual-only | N/A — verified in Actions run | N/A |
| DEPLOY-06 | CD workflow: image built, tagged `sha-*`, pushed to GHCR | manual-only | N/A — verify in GHCR packages tab | N/A |
| DEPLOY-06 | Trivy scan runs, blocks on HIGH/CRITICAL | manual-only | N/A — verify in Actions run + Security tab | N/A |
| DEPLOY-06 | Dev kustomization updated with new SHA tag | smoke | `git log --oneline k8s/overlays/dev/kustomization.yaml` | N/A |
| DEPLOY-06 | ArgoCD picks up manifest change, dev syncs | manual-only | `kubectl get pods -n civpulse-dev` after sync | N/A |
| DEPLOY-06 | Prod requires `v*` tag (not triggered by merge) | manual-only | N/A — verify by checking prod overlay is unchanged post-merge | N/A |

**Justification for manual-only:** CI/CD pipeline behavior cannot be unit tested. Verification is performed by observing GitHub Actions run results, GHCR tags, and ArgoCD sync status after a PR merge and a `v*` tag push.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q` (local — 1.57s, 548 tests)
- **Per wave merge:** Full suite via `uv run pytest tests/`
- **Phase gate:** Phase verification is the first PR merge that triggers the full CD pipeline

### Wave 0 Gaps

- [ ] `[tool.ruff]` section in `pyproject.toml` — needed before `ci.yml` is safe to merge
- [ ] `.trivyignore` populated — needed before `cd.yml` can pass the scan step

*(Existing test infrastructure covers all phase requirements. No new test files needed.)*

---

## Project Constraints (from CLAUDE.md)

These directives apply to this phase's implementation:

| Directive | Impact on Phase 21 |
|-----------|-------------------|
| Always use `uv` for Python tasks | `ci.yml` must use `uv sync` and `uv run pytest` — never `pip install` or `python -m pytest` |
| Always use `ruff` to lint Python code | `ci.yml` runs ruff before pytest |
| Never use system Python | GitHub runner uses Python via `astral-sh/setup-uv`, not system Python |
| Always use Conventional Commits | Automated manifest commits use `chore(deploy):` prefix |
| Git commits on branches unless requested to commit to main | Automated deploy commits go directly to `main` — this is intentional and explicitly authorized by D-01 |
| After UI changes, visually verify with Playwright | Not applicable — this phase has no UI |

---

## Sources

### Primary (HIGH confidence)
- GitHub Releases API (queried 2026-03-30) — all action commit SHAs verified against `gh api repos/{owner}/{repo}/git/ref/tags/{tag}`
- `astral-sh/setup-uv` README (GitHub API, base64 decoded 2026-03-30) — caching configuration, python-version input, enable-cache usage
- `astral-sh/ruff-action` README (GitHub API, base64 decoded 2026-03-30) — input options, installation behavior
- `aquasecurity/trivy-action` README (GitHub API, base64 decoded 2026-03-30) — exit-code, severity, trivyignores, SARIF output
- Phase 21 CONTEXT.md (D-01 through D-10) — locked decisions
- Phase 19 CONTEXT.md (D-08, D-09, D-11) — GHCR repo name, SHA tag convention, public image
- Phase 20 CONTEXT.md (D-04, D-05) — Kustomize overlays structure, ArgoCD auto-sync
- Direct file inspection: `Dockerfile`, `k8s/overlays/*/kustomization.yaml`, `k8s/overlays/*/argocd-app.yaml`, `pyproject.toml`, `tests/conftest.py`
- Local test run: `uv run pytest tests/ -x -q` — 548 passed, 2 skipped, confirmed no DB/network dependencies
- Fiona lib inspection: `fiona.libs/` contains bundled GDAL — no system GDAL needed in CI runner

### Secondary (MEDIUM confidence)
- GitHub Actions documentation patterns for `paths-ignore`, concurrency guards, `[skip ci]` commit message convention — well-established patterns, consistent across multiple official examples
- `kustomize/v5.8.1` binary download URL verified via GitHub Releases API

### Tertiary (LOW confidence)
- CVE IDs for `.trivyignore` — not yet determined; requires running Trivy against the actual base image

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all action versions and SHAs verified via GitHub Releases API on 2026-03-30
- Architecture: HIGH — patterns derived from official action READMEs + existing repo files
- Pitfalls: HIGH — pitfalls 1-6 are verified failure modes from official docs and direct code inspection
- CVE suppression list: LOW — actual CVE IDs require a live Trivy scan

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (action SHAs are immutable once verified; Docker base image CVEs may change daily)
