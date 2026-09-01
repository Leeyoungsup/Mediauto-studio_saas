# Production Deployment Guide

This guide covers the production settings that should be explicit before
running MeDIAuto Studio SaaS outside a local workstation.

## Runtime Layout

- Run the FastAPI app with a process manager or service supervisor.
- Put a TLS-terminating reverse proxy in front of the app.
- Use MongoDB authentication and TLS for every production database connection.
- Store WSI uploads, tile cache, AI results, and secrets on backed-up volumes.
- Keep model files and Philips SDK dependencies outside user-writable paths.

## Required Environment Variables

| Variable | Production guidance |
| --- | --- |
| `MONGO_URI` | Use an authenticated TLS URI. Example below. |
| `MONGO_DB_NAME` | Use a deployment-specific database name. |
| `JWT_SECRET_KEY` | Inject from a secret manager. Do not rely on auto-generated local files. |
| `FIELD_ENCRYPTION_KEY` | Inject from a secret manager. Keep stable across restarts and backups. |
| `AUTH_PEPPER` | Inject from a secret manager. Changing it invalidates password verification for existing users. |
| `MEDIA_SIGNING_KEY` | Set explicitly if supported by the running build; otherwise it is derived from the JWT secret. |
| `CORS_ORIGINS` | Empty for same-origin deployments, or a comma-separated allowlist. |
| `TRUSTED_PROXIES` | Comma-separated reverse proxy IPs allowed to supply `X-Forwarded-For`. |
| `BLOCKED_IPS` | Additional comma-separated IP/CIDR denylist. `207.175.151.181` is blocked by default. |
| `MEDIAUTO_404_RATE_LIMIT_MAX` | Maximum public/static 404 responses per IP and window. Default: `30`. |
| `MEDIAUTO_404_RATE_LIMIT_WINDOW_SECONDS` | Repeated-404 window in seconds. Default: `60`. |
| `UPLOAD_DIR` | Persistent WSI storage. |
| `TILES_DIR` | Persistent or rebuildable tile cache storage. |
| `AI_RESULTS_DIR` | Persistent AI result cache storage. |
| `MODEL_DIR` | Read-only directory containing the model files listed in `backend/model_manifest.json`. |
| `TILE_CACHE_QUOTA_BYTES` | Disk quota for tile cache eviction. Use `0` only when another cleanup job exists. |
| `MAX_UPLOAD_BYTES` | Match institutional policy and reverse proxy upload limits. |
| `JPEG_CONVERSION_QUALITY` | Internal JPEG quality for JPG-to-pyramidal-TIFF conversion. Default: `100`. |

## MongoDB TLS and Authentication

Use a MongoDB user with the least privileges needed by the app database.

Example URI:

```text
mongodb://mediauto_app:<password>@mongo01.example.local:27017/medicus_studio?authSource=admin&tls=true&tlsCAFile=C:%5Ccerts%5Cca.pem
```

For a replica set:

```text
mongodb://mediauto_app:<password>@mongo01.example.local:27017,mongo02.example.local:27017,mongo03.example.local:27017/medicus_studio?replicaSet=rs0&authSource=admin&tls=true&tlsCAFile=C:%5Ccerts%5Cca.pem
```

Recommended MongoDB controls:

- Enable `authorization`.
- Enable TLS with a private CA or enterprise certificate chain.
- Create a dedicated application user for the app database.
- Use separate backup or audit users instead of reusing the app user.
- Back up `users`, `sessions`, `audit_logs`, `slides`, `project_infos`, `folder_ai_configs`, `annotation_required_regions`, `patch_annotation_status`, `patch_cell_annotations`, and `user_ai_edits`.
- Protect `audit_logs` from update/delete with database role separation where possible.

## Secret Management

The app can create `backend/.secrets.json` for local development. Production
should instead inject secrets through the service environment.

Required properties:

- Secrets must survive restarts and redeployments.
- Secrets must be excluded from normal file backups unless the backup is encrypted and access-controlled.
- `JWT_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, and `AUTH_PEPPER` must be rotated through a planned migration.
- Restoring a database without restoring matching secrets can break login, MFA, encrypted fields, or token validation.

Suggested Windows service environment pattern:

```powershell
$env:MONGO_URI = "mongodb://mediauto_app:<password>@mongo01:27017/medicus_studio?authSource=admin&tls=true&tlsCAFile=C:\certs\ca.pem"
$env:MONGO_DB_NAME = "medicus_studio"
$env:JWT_SECRET_KEY = "<64+ random URL-safe chars>"
$env:FIELD_ENCRYPTION_KEY = "<32+ random URL-safe chars>"
$env:AUTH_PEPPER = "<32+ random URL-safe chars>"
$env:CORS_ORIGINS = ""
$env:TRUSTED_PROXIES = "10.10.0.5"
```

## Reverse Proxy Requirements

The reverse proxy should set:

- TLS 1.2 or newer.
- HSTS after HTTPS is confirmed stable.
- `X-Forwarded-For` and `X-Forwarded-Proto`.
- Upload body limits at least as large as `MAX_UPLOAD_BYTES`.
- Long enough read/write timeouts for large chunk uploads.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options` or CSP `frame-ancestors`, `Referrer-Policy`, and a deployment-specific CSP.

Set `TRUSTED_PROXIES` to the proxy IPs. Leave it empty if clients connect
directly to Uvicorn; otherwise an attacker could spoof client IP headers.

## Philips Bridge Operations

Philips iSyntax support runs the Philips SDK in a separate Python 3.7 process.

Important environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PHILIPS_CONDA_ENV` | OS-specific | `philips-sdk-py38` on Linux and `philips-sdk-py37` on Windows. |
| `PHILIPS_PYTHON` | empty | Absolute path to the Python executable that can import the Philips SDK. |
| `MEDIAUTO_PHILIPS_SDK_SOURCE` | empty | Licensed SDK directory or ZIP/TAR used only during bootstrap. |
| `MEDIAUTO_ACCEPT_PHILIPS_EULA` | `0` | Must be set to `1` by the operator after reviewing the SDK EULA. |
| `PHILIPS_VIEW` | `display` | OpenPhi view mode. |
| `PHILIPS_BRIDGE_MODE` | `auto` | `auto`, `persistent`, or `cli`. |
| `PHILIPS_TIMEOUT_SECONDS` | `120` | Per-command timeout. |
| `PHILIPS_START_TIMEOUT_SECONDS` | `30` | Persistent bridge startup timeout. |
| `PHILIPS_STOP_GRACE_SECONDS` | `3` | Grace period before killing a stuck bridge process. |
| `PHILIPS_LOG_STDERR` | `1` | Forward bridge stderr to the FastAPI logger. |
| `PHILIPS_SERVER_LOG_COMMANDS` | `0` | Emit per-command bridge timing logs from the Python 3.7 side server. |
| `PHILIPS_SHARED_MEMORY` | `1` | Use Windows shared memory for large region reads in persistent mode. |
| `PHILIPS_BYTES_MAX_PIXELS` | `4194304` | Pixel threshold for inline PNG response vs file/shared memory transport. |

Operational guidance:

- Prefer `PHILIPS_BRIDGE_MODE=persistent` after the SDK environment is stable.
- Use `PHILIPS_BRIDGE_MODE=cli` only for debugging or isolating process lifetime issues.
- Keep `PHILIPS_LOG_STDERR=1` in production; enable `PHILIPS_SERVER_LOG_COMMANDS=1` only while diagnosing slow slide reads.
- Monitor bridge timeout errors. They usually indicate SDK hangs, invalid slide input, or storage latency.

## Backup and Restore Notes

Back up these together:

- MongoDB database.
- `UPLOAD_DIR`.
- `AI_RESULTS_DIR`.
- Required annotation/export files under the configured annotation storage.
- Production secrets.

`TILES_DIR` can be treated as rebuildable cache if disk pressure is high, but
restoring it improves cold-start viewer performance.

## Preflight Checklist

- MongoDB requires authentication and TLS.
- Production secrets are injected from a controlled store.
- `.secrets.json` is not the primary production secret source.
- Reverse proxy TLS and upload limits are configured.
- `TRUSTED_PROXIES` matches the actual proxy IPs.
- Backups include database, WSI files, AI results, and secrets.
- A restore drill has verified login, MFA, slide open, tile rendering, AI result loading, and audit chain verification.
