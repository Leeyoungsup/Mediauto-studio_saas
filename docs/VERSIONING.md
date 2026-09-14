# Versioning

MeDIAuto Studio uses a single version metadata file at the repository root:

```text
version.json
```

The backend reads this file through `backend/app/version.py`.

The in-app `/version` page reads every release section from `CHANGELOG.md`
through `/api/version-history`. Do not maintain a separate frontend release
list; updating the changelog automatically updates the page after restart.

## Current Version

```text
3.1.0
```

- Release channel: `production`
- Release date: `2026-09-14`

## Version Policy

The project follows Semantic Versioning:

- **MAJOR**: incompatible datastore, configuration, API, or deployment changes.
- **MINOR**: backward-compatible user or operator features.
- **PATCH**: backward-compatible fixes and internal improvements.

Version 3.0.0 requires annotation clients to load the current ETag and send it
as `If-Match` when saving. Missing revisions return HTTP 428 and stale revisions
return HTTP 409. This incompatible API contract requires a major version.
Deploy the backend and frontend together and reload open browser pages after
exporting any unsaved edits. Existing annotation data requires no migration.

Version 2.0.0 is a major release because PostgreSQL becomes the only supported
datastore and the previous database configuration and runtime dependencies are
removed.

## Update Checklist

1. Update `version.json`.
2. Review commits since the previous release and add a matching section to `CHANGELOG.md`.
3. Run backend syntax checks.
4. Run the full backend test suite and verify `/api/version` and `/api/health`.
5. Merge the release branch into `main`.
6. Create an annotated Git tag after the merge:

```bash
git tag -a v3.1.0 -m "MeDIAuto Studio 3.1.0"
git push origin v3.1.0
```

Do not tag before the target commit is present on `main`. A version bump does
not migrate or copy production data; deployment backups and Alembic migration
checks remain separate release gates.

## Writing Release Notes

Use the following section format so the API parser and version page can render
the release automatically:

```markdown
## [2.1.0] - YYYY-MM-DD

### Added

- User-visible feature.

### Changed

- Important workflow or deployment change.

### Fixed

- Corrected behavior.
```

Before writing the entry, review the full commit range rather than relying on
memory. For example, after tagging 3.0.0:

```bash
git log --format='%h %ad %s' --date=short v3.0.0..HEAD
```

Summarize internal commits into user- or operator-meaningful bullets. Keep
breaking configuration and datastore changes in a `Breaking Changes` section.

## Exposed Endpoints

```text
GET /api/version
GET /api/health
```

`/api/version` returns the full version metadata. `/api/health` includes the active version string.
