# Production Deployment Guide

This guide covers the production settings that should be explicit before
running MeDIAuto Studio SaaS outside a local workstation.

## Runtime Layout

- Run the FastAPI app with a process manager or service supervisor.
- Put a TLS-terminating reverse proxy in front of the app.
- Use PostgreSQL 18 with TLS, authentication, and least-privilege roles.
- Store WSI uploads, tile cache, AI results, and secrets on backed-up volumes.
- Keep model files and Philips SDK dependencies outside user-writable paths.

## Required Environment Variables

| Variable | Production guidance |
| --- | --- |
| `POSTGRES_URI` | SQLAlchemy async URI, normally `postgresql+asyncpg://...`. Require TLS for remote connections. |
| `POSTGRES_POOL_SIZE` | Baseline connection pool size. Default: `10`. |
| `POSTGRES_MAX_OVERFLOW` | Temporary connections above the pool size. Default: `20`. |
| `JWT_SECRET_KEY` | Inject from a secret manager. Do not rely on auto-generated local files. |
| `FIELD_ENCRYPTION_KEY` | Keep stable across restarts and backups. |
| `AUTH_PEPPER` | Changing it invalidates password verification for existing users. |
| `MEDIA_SIGNING_KEY` | Set explicitly or let the app derive it from the JWT secret. |
| `CORS_ORIGINS` | Empty for same-origin, or a comma-separated allowlist. |
| `TRUSTED_PROXIES` | Proxy IPs allowed to supply `X-Forwarded-For`. |
| `BLOCKED_IPS` | Additional comma-separated IP/CIDR denylist. |
| `UPLOAD_DIR` | Persistent WSI storage. |
| `TILES_DIR` | Persistent or rebuildable tile cache storage. |
| `AI_RESULTS_DIR` | Persistent AI result cache storage. |
| `MODEL_DIR` | Read-only AI model directory. |
| `TILE_CACHE_QUOTA_BYTES` | Tile-cache disk quota. |
| `MAX_UPLOAD_BYTES` | Match reverse-proxy upload limits. |
| `JPEG_CONVERSION_QUALITY` | JPG-to-pyramidal-TIFF JPEG quality. Default: `100`. |

## PostgreSQL Security

- Use a dedicated application role and database.
- Require TLS for connections that leave the host.
- Bind native local installations to loopback unless remote access is required.
- Restrict schema changes to the Alembic deployment role where practical.
- Grant the application role no superuser, role-management, or database-creation privileges.
- Protect database dumps because they contain account, clinical, annotation, and audit data.

Example remote URI:

```text
postgresql+asyncpg://mediauto_app:<url-encoded-password>@db.example.local:5432/medicus_studio?ssl=require
```

## Secret Management

The app can create `backend/.secrets.json` for local development. Production
should inject secrets through the service environment. Secrets must survive
restart and restore. Restoring PostgreSQL without the matching secrets can
break login, MFA decryption, token validation, or audit verification.

## Reverse Proxy Requirements

- TLS 1.2 or newer and HSTS after HTTPS is stable.
- Correct `X-Forwarded-For` and `X-Forwarded-Proto` headers.
- Upload limits at least as large as `MAX_UPLOAD_BYTES`.
- Long enough timeouts for chunk uploads.
- `X-Content-Type-Options`, CSP/frame restrictions, and `Referrer-Policy`.

Only list the actual proxy addresses in `TRUSTED_PROXIES`.

## Philips Bridge Operations

Philips iSyntax uses a separate licensed SDK environment: Python 3.8 on Linux
and Python 3.7 on Windows. Prefer persistent bridge mode after its smoke test
passes. Keep bridge stderr logging enabled and investigate repeated timeouts as
SDK, storage, or invalid-slide failures.

## Backup and Restore

Back up these items together:

- PostgreSQL using `pg_dump --format=custom`.
- `UPLOAD_DIR` and `AI_RESULTS_DIR`.
- Required annotation/export files outside PostgreSQL.
- Production secrets in a separately protected backup.

`TILES_DIR` is rebuildable, although restoring it improves cold-start viewer
performance. Validate backups with `pg_restore --list` and perform periodic
restore drills covering login, MFA, slide open, AI results, annotations, and
audit-chain verification.

## Preflight Checklist

- PostgreSQL authentication and TLS policy are configured.
- `alembic upgrade head` completed successfully.
- Production secrets come from a controlled store.
- Reverse proxy and upload limits are configured.
- Database, WSI, AI results, and secrets have tested backups.
- `/api/health` returns success and the log reports PostgreSQL connected.
