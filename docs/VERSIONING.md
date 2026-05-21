# Versioning

MeDIAuto Studio uses a single version metadata file at the repository root:

```text
version.json
```

The backend reads this file through `backend/app/version.py`.

## Current Version

```text
1.1.61
```

## Update Checklist

1. Update `version.json`.
2. Add a matching section to `CHANGELOG.md`.
3. Run backend syntax checks.
4. Merge `dev` into `main`.
5. Create a Git tag after the merge if needed:

```bash
git tag v1.1.61
git push origin v1.1.61
```

## Exposed Endpoints

```text
GET /api/version
GET /api/health
```

`/api/version` returns the full version metadata. `/api/health` includes the active version string.
