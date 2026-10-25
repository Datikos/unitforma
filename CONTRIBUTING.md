# Contributing

- Branch from `main`, open a pull request, keep PRs scoped to one backlog task (`docs/architecture/plan-v0.1.md` §15).
- CI must be green: backend lint/tests, frontend lint/tests/builds, Compose validation, image builds.
- Architecture decisions go into `docs/adr/NNNN-title.md` using the template in `docs/adr/0000-template.md`.
- Definition of done: tests, migration backward compatible, OpenAPI updated, docs/ADR touched if a decision changed.
