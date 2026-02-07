# Release Checklist (v0.1.0)

## Determinism & Safety
- [ ] No background threads
- [ ] No schedulers / cron
- [ ] No random backoff
- [ ] Hop caps enforced
- [ ] Throttling is bounded

## Permissions
- [ ] No write-to-world paths
- [ ] No Operator layer code
- [ ] No hidden escalation
- [ ] Read-only connectors only

## Observability
- [ ] Metrics are read-only
- [ ] Audit logs are append-only
- [ ] No metrics trigger behavior

## Tests & CI
- [ ] python -m unittest passes locally
- [ ] CI green on main
- [ ] Load simulation terminates cleanly
