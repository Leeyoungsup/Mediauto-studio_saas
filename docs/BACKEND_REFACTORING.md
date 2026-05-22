# Backend Refactoring Notes

## Current Direction

The backend is being refactored in small behavior-preserving steps.  The main
goal is to reduce the size of route modules and move reusable business logic
into domain modules that can be tested and maintained independently.

## Target Boundaries

- `app/routers/*`: HTTP request parsing, auth dependencies, and response shape.
- `app/clinical_info.py`: case-name extraction and case-level clinical metadata.
- `app/path_utils.py`: upload-relative path resolution and filename validation.
- `app/project_utils.py`: project metadata shaping and project-level AI task
  normalization.
- `app/slide_store.py`: slide database persistence and serialization.
- `app/tile_generator.py`, `app/tile_worker.py`, `app/routers/tiles.py`: tile
  generation and serving.
- `app/ai_pipelines/*`: long-running AI task execution.
- `app/resource_utils.py`: small resource cleanup helpers shared by workers.

## First Refactor Pass

- Extracted case-level clinical info helpers out of `routers/slides.py`.
- Extracted upload path and filename validation helpers out of `routers/slides.py`.
- Added resource cleanup helpers for OpenSlide/PIL/file-like objects.
- Updated VS IHC cleanup to use the shared helper instead of local ad-hoc close
  handling.

## Second Refactor Pass

- Moved thumbnail and preview endpoints to `routers/slide_media.py`.
- Moved project and folder management endpoints to `routers/projects.py`.
- Moved file delete/status/move endpoints to `routers/file_operations.py`.
- Moved annotation class and annotation JSON storage endpoints to
  `routers/annotation_storage.py`.
- Kept the public `/api/slides/*` URL surface unchanged by mounting the new
  routers under the same prefix.

## Next Safe Splits

- Move upload/open endpoints into a dedicated ingestion router and service.
- Replace scattered `print()` diagnostics with a shared logger once behavior is
  stable.
