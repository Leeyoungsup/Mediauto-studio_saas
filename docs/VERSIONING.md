# Versioning

MeDIAuto Studio uses a single version metadata file at the repository root:

```text
version.json
```

The backend reads this file through `backend/app/version.py`.

## Current Version

```text
2.0.0
```

- Release channel: `production`
- Release date: `2026-09-01`

## Version Policy

The project follows Semantic Versioning:

- **MAJOR**: incompatible datastore, configuration, API, or deployment changes.
- **MINOR**: backward-compatible user or operator features.
- **PATCH**: backward-compatible fixes and internal improvements.

Version 2.0.0 is a major release because PostgreSQL becomes the only supported
datastore and the previous database configuration and runtime dependencies are
removed.

## Update Checklist

1. Update `version.json`.
2. Add a matching section to `CHANGELOG.md`.
3. Run backend syntax checks.
4. Run the full backend test suite and verify `/api/version` and `/api/health`.
5. Merge the release branch into `main`.
6. Create an annotated Git tag after the merge:

```bash
git tag -a v2.0.0 -m "MeDIAuto Studio 2.0.0"
git push origin v2.0.0
```

Do not tag before the target commit is present on `main`. A version bump does
not migrate or copy production data; deployment backups and Alembic migration
checks remain separate release gates.

## Exposed Endpoints

```text
GET /api/version
GET /api/health
```

`/api/version` returns the full version metadata. `/api/health` includes the active version string.
