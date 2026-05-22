# Backend Refactoring Notes

## Current Direction

The backend is being refactored in small behavior-preserving steps.  The main
goal is to reduce the size of route modules and move reusable business logic
into domain modules that can be tested and maintained independently.

## Target Boundaries

- `app/routers/*`: HTTP request parsing, auth dependencies, and response shape.
- `app/clinical_info.py`: case-name extraction and case-level clinical metadata.
- `app/slide_store.py`: slide database persistence and serialization.
- `app/tile_generator.py`, `app/tile_worker.py`, `app/routers/tiles.py`: tile
  generation and serving.
- `app/ai_pipelines/*`: long-running AI task execution.
- `app/resource_utils.py`: small resource cleanup helpers shared by workers.

## First Refactor Pass

- Extracted case-level clinical info helpers out of `routers/slides.py`.
- Added resource cleanup helpers for OpenSlide/PIL/file-like objects.
- Updated VS IHC cleanup to use the shared helper instead of local ad-hoc close
  handling.

## Next Safe Splits

- Move project and folder management endpoints out of `routers/slides.py`.
- Move upload/delete/move file operations into a file-management service.
- Move media thumbnail/preview helpers into a dedicated media module.
- Replace scattered `print()` diagnostics with a shared logger once behavior is
  stable.
