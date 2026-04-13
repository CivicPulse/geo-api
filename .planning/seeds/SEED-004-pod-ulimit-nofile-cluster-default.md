---
id: SEED-004
status: dormant
planted: 2026-04-13
planted_during: v1.5 Prod/Dev Bootstrap & K8s Jobs (first-run bootstrap on thor)
trigger_when: another pod hits "Too many open files" OR k3s/containerd runtime config changes OR any service with high thread fan-out gets added
scope: medium
---

# SEED-004: Raise pod-level `nofile` limit instead of capping per-service thread counts

## Why This Matters

During v1.5 first-run bootstrap on 2026-04-13, the `valhalla` Deployment's serving container crashed repeatedly with:
```
Too many open files (src/ipc_listener.cpp:297)
Too many open files (src/epoll.cpp:38)
```

Root cause: `valhalla_service` defaulted to `server_threads = nproc` on thor, which is 40+ cores. Each zmq/epoll worker opens ~25 file descriptors. 40 × 25 = 1000 fds, saturating the **1024-soft-nofile default** baked into containerd's runtime config. The pod died before serving a single request.

Pragmatic fix applied (commit `e131461`): capped `server_threads=8` in the Deployment env. Gets valhalla serving with ~200 fds, comfortably under the limit. **But this is a workaround, not a fix.**

The real issue is cluster-wide:
1. **Every service with high thread fan-out has the same ceiling.** Anything that forks per-core workers (Python multiprocessing, Go worker pools sized to GOMAXPROCS, Node cluster modules, any ZMQ-based app) will hit 1024 fds on a many-core node.
2. **Kubernetes doesn't have a first-class way to set pod nofile.** `securityContext.sysctls` doesn't include `fs.nr_open`; `ulimits` isn't in PodSpec at all. The only supported path today is **runtime handler config** — i.e., edit `containerd`'s config.toml to set `[plugins."io.containerd.grpc.v1.cri".containerd.default_runtime_options] LimitNOFILE = 65536` or similar.
3. **k3s bakes its own containerd.** k3s generates containerd config from a template; raising nofile means editing `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl` and restarting k3s. Affects all pods on the node.

Options when addressing this:
- **A. Cluster-wide nofile bump.** Edit the k3s containerd template to set LimitNOFILE=65536, restart k3s-agent on thor. All current and future pods benefit. Single-point fix. Risk: a rogue container could leak fds up to the new ceiling before failing (but 65536 is industry-standard, used by defaults in AKS/EKS/GKE).
- **B. Per-service workaround acceptance.** Document the pattern: any service with per-core thread fan-out must explicitly cap thread count via env var. Less invasive, but leaky abstraction — requires reading every new service's docs for "what's the thread variable".
- **C. Privileged initContainer that calls `prlimit`.** Run a one-shot container as root that raises the main container's RLIMIT_NOFILE before handoff. Complex, requires privilege, k8s fights this pattern.

Option A is the right long-term choice.

## When to Surface

**Trigger:** The next time any pod in this cluster hits "Too many open files", OR any change to k3s / containerd runtime config, OR the next addition of a service with high thread fan-out (OSM stack expansions, ML model serving, WebSocket servers).

This seed should be presented during `/gsd-new-milestone` when the milestone scope matches any of:
- Cluster infrastructure / runtime config work
- Adding a new service that forks workers per core
- Performance / scaling phase where we re-examine resource limits
- DR or cluster rebuild work that reconstructs thor's container runtime

## Scope Estimate

**Medium** — edit the k3s containerd template, restart k3s-agent (brief node disruption), verify pods survive a rollout. Runtime config change requires operator scheduling and documentation of the new default. Also need to undo the `server_threads=8` cap in valhalla.yaml at the same time so we reap the benefit (or leave it capped and treat this as purely defensive headroom).

## Breadcrumbs

- `k8s/osm/base/valhalla.yaml` — the `server_threads=8` workaround is at line ~34 (in the env list)
- Commit `e131461` — applied the workaround, with detailed context in the commit message
- k3s containerd template: `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl` on thor (needs to be created if the default is sufficient)
- k3s docs: <https://docs.k3s.io/advanced#configuring-containerd> (confirm URL when planting phase)

## Notes

Observed nofile usage per worker in the gis-ops valhalla image: ~25 fds (zmq_pair + epoll + tile_extract mmap). With 324 tiles loaded, that's additional per-tile fd overhead. The 8-thread cap gives us headroom on a 1024-limit; under a 65536-limit we could go back to nproc.

Context7 lookup might be useful at planning time for the exact k3s config path for containerd LimitNOFILE — verify before editing.

Related: not all pods on thor may need the raise. Currently affected: valhalla. Not yet tested: nominatim (has its own postgres + apache which are lower-fd), tile-server (renderd is lower-fd), geo-api (Python uvicorn is lower-fd). But the raise is essentially free — no reason not to do it cluster-wide.
