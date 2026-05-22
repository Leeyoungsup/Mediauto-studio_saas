# Changelog

All notable changes to MeDIAuto Studio are tracked here.

## [1.1.87] - 2026-05-22

### Fixed

- Fixed a broken `api.js` comment that accidentally disabled `tileUrl()` and stopped tile image requests.
- Bumped frontend module cache keys so the restored API module loads immediately.

## [1.1.86] - 2026-05-22

### Fixed

- Restored initial visible tile requests after thumbnail-first viewer loading.
- Added validation for stage dimensions before calculating visible tile ranges.
- Bumped frontend module cache keys so the fixed tile loader is used immediately.

## [1.1.85] - 2026-05-22

### Fixed

- Fixed a syntax regression in `tile-viewer.js` that prevented the AI module from loading.
- Replaced broken/mojibake AI viewer help markup with ASCII-safe English HTML.
- Bumped frontend module cache keys so the corrected viewer module loads immediately.

## [1.1.84] - 2026-05-22

### Changed

- AI and annotation viewer minimaps now use the same 300px NDP thumbnail as the main fallback.
- Removed 2048px thumbnail requests from AI and annotation viewer startup paths.
- Added simple minimap URL dedupe so repeated load calls for the same slide do not start duplicate thumbnail requests.

## [1.1.83] - 2026-05-22

### Changed

- Refactored tile viewer loading into foreground visible-tile work and throttled background overview preload work.
- Delayed overview preload until after the initial viewport render path starts.
- Limited overview preload to two concurrent background tile requests so zoom/pan tiles stay responsive.
- Reordered overview preload around the current view center instead of simple row order.

## [1.1.82] - 2026-05-22

### Changed

- Reused the loaded minimap thumbnail as the main viewer fallback image.
- Removed the duplicate 300px thumbnail request from the tile viewer startup path.

## [1.1.81] - 2026-05-22

### Fixed

- Restored 2048px NDP-matched thumbnails for AI and annotation minimaps.
- Reverted the broad NDPI thumbnail clamp so only viewer startup fallback remains on the fast 300px path.

## [1.1.80] - 2026-05-22

### Fixed

- Clamped NDPI thumbnail URL builders to 300px so stale or indirect callers cannot request 2048px matched thumbnails.
- Bumped frontend module cache keys again to force the corrected API URL builder into the browser.

## [1.1.79] - 2026-05-22

### Fixed

- Removed remaining 2048px minimap thumbnail requests from AI and annotation viewer startup paths.
- Bumped frontend module cache keys so browsers do not keep stale viewer modules.
- Cleaned viewer/API comments to ASCII-safe text to avoid source mojibake in editors.

## [1.1.78] - 2026-05-22

### Changed

- Viewer startup no longer requests the 2048px preview fallback.
- NDPI slides now use only the fast 300px NDP-matched thumbnail as the initial main viewer fallback.
- Viewer module cache-busting was bumped so the simplified startup path loads immediately.

## [1.1.77] - 2026-05-22

### Fixed

- Viewer startup now begins overview tile preload as soon as the fast NDP-matched thumbnail is painted, instead of waiting for the 2048px preview.
- The 2048px preview still loads in the background and replaces the initial thumbnail when ready.

## [1.1.76] - 2026-05-22

### Fixed

- NDPI viewer startup no longer paints raw thumbnails into the main viewer while NDP matching is enabled.
- Viewer startup now paints a fast 300px matched thumbnail first, then waits for the 2048px preview before starting overview tile preload.
- Slide preview endpoints now reuse the cached 2048 thumbnail/NDP-match image when available instead of regenerating the preview every time.
- AI and annotation viewer module cache-busting was bumped so browsers load the updated tile viewer immediately.

## [1.1.75] - 2026-05-22

### Changed

- Split slide thumbnail and preview endpoints into `app/routers/slide_media.py`.
- Split project and folder management endpoints into `app/routers/projects.py`.
- Split file delete/status/move endpoints into `app/routers/file_operations.py`.
- Split annotation class and annotation JSON storage endpoints into `app/routers/annotation_storage.py`.
- Extracted project metadata and project-level AI task helpers into `app/project_utils.py`.
- Cleaned broken encoded backend source comments/messages in the remaining slide router so backend compilation is stable.

## [1.1.74] - 2026-05-22

### Changed

- Started backend refactoring by extracting case-level clinical info helpers from the large slide router into `app/clinical_info.py`.
- Extracted upload path and filename validation helpers into `app/path_utils.py`.
- Added shared backend resource cleanup helpers in `app/resource_utils.py` and applied them to VS IHC slide cleanup.
- Added backend refactoring notes documenting the target router/service boundaries.

## [1.1.73] - 2026-05-22

### Fixed

- NDPI files now automatically request NDP-matched thumbnail/preview images through shared API helpers.
- AI, Tissue Annotation, Cell Annotation, and Data Linkage bundles were cache-busted so the updated thumbnail routing is used immediately.
- Viewer fallback thumbnails avoid showing raw-color placeholders for NDPI slides before the NDP-matched image loads.

## [1.1.72] - 2026-05-22

### Changed

- AI, Tissue Annotation, and Cell Annotation now instantiate separate viewer entry classes instead of importing the shared tile engine directly.
- Viewer page capabilities are defined in a small shared module so page-specific behavior can be separated without changing the tile rendering core.

## [1.1.71] - 2026-05-22

### Fixed

- VS IHC now closes its direct OpenSlide handle in all exit paths and releases the shared slide handle after the task finishes.
- Default OpenSlide handle retention was reduced from 8 slides / 30 minutes to 4 slides / 5 minutes, with `MAX_OPEN_SLIDES` and `IDLE_SLIDE_TTL_SECONDS` environment overrides.

## [1.1.70] - 2026-05-22

### Fixed

- VS IHC now uses bounded patch prefetching instead of queueing every patch read at once, reducing memory spikes during large virtual stain jobs.
- VS IHC GAN batch tensors are released immediately after each batch is splatted into the tile streamer.
- VS IHC read-ahead can be tuned with `VS_IHC_PREFETCH_LIMIT` for very memory-constrained machines.

## [1.1.69] - 2026-05-22

### Fixed

- Viewer first paint now uses the already-loaded 300px sidebar thumbnail as a temporary placeholder.
- Tile preloading now waits for a dedicated 2048px viewer thumbnail/preview to paint, with a short fallback timeout to avoid stalls.

## [1.1.68] - 2026-05-22

### Fixed

- Viewer 2048px thumbnail/preview preload images are now tracked as in-flight resources so they are not dropped before painting.
- AI and Annotation pages now load the refreshed tile viewer bundle.

## [1.1.67] - 2026-05-21

### Fixed

- Viewer canvas fallback thumbnails now use dedicated 2048px image requests instead of reusing the 300px sidebar list thumbnails.
- AI and Annotation pages now load the refreshed tile viewer bundle.

## [1.1.66] - 2026-05-21

### Fixed

- Data Linkage now loads the refreshed API helper so linked-image thumbnail strips use 300px requests; the main preview remains 2048px for zooming.

## [1.1.65] - 2026-05-21

### Fixed

- Thumbnail URL helpers now honor small sizes such as 300px instead of forcing every thumbnail request to at least 2048px.

## [1.1.64] - 2026-05-21

### Fixed

- Completed AI task results are released from process memory after the client downloads them, and finished task records are expired after a short TTL.
- OpenSlide handles are now bounded by idle/LRU eviction in `SlideManager`.
- Large PIL/OpenSlide image intermediates in tile, thumbnail, and AI patch paths are closed more aggressively.
- Small in-memory user/tile access caches now prune stale entries.

## [1.1.63] - 2026-05-21

### Fixed

- Slide tiles and thumbnails now composite transparent outside-slide padding onto white before RGB conversion, preventing black letterbox areas in the viewer.
- Tile cache marker version was bumped so old black-padding tile caches regenerate.

## [1.1.62] - 2026-05-21

### Changed

- Compact slide lists, Home recent slide cards, and Data Linkage thumbnail strips now request 300px thumbnails instead of 2048px images.

## [1.1.61] - 2026-05-21

### Added

- Added `backend/scripts/compact_ai_result_cache.py` to compact existing object-cell AI result JSON cache files across `backend/ai_results`.

## [1.1.60] - 2026-05-21

### Changed

- AI cell results are now stored and transferred in a compact array format, then normalized on the frontend, dramatically reducing very large PD-L1 JSON payloads.
- Existing large PD-L1 cache files are compacted on load when needed.

## [1.1.59] - 2026-05-21

### Fixed

- Large AI result JSON downloads now buffer byte chunks and decode once, avoiding browser `Invalid string length` errors caused by repeated string concatenation.

## [1.1.58] - 2026-05-21

### Added

- AI result JSON downloads now update the AI progress bar with percent or downloaded MB while large results are fetched.

## [1.1.57] - 2026-05-21

### Fixed

- AI task status responses now use FastAPI's native JSON response path.
- Empty or malformed AI task status/result responses are retried briefly before surfacing an error.

## [1.1.56] - 2026-05-21

### Fixed

- AI task polling no longer embeds large result JSON in `/api/ai/task/{task_id}` responses.
- AI, Annotation, PD-L1, IHC, and VS IHC viewers now fetch the large task result once from `/api/ai/task/{task_id}/result` after completion.

## [1.1.55] - 2026-05-21

### Fixed

- Quanti PD-L1 start/status polling now reports empty or malformed API responses clearly instead of showing the browser's generic JSON parse error.

## [1.1.54] - 2026-05-21

### Fixed

- Color-matched slides now use the already-loaded raw thumbnail as the immediate viewer fallback while corrected thumbnails/previews are generated.
- Viewer first paint now uses a white background instead of black when no fallback image is available yet.

## [1.1.53] - 2026-05-21

### Added

- AI and Annotation minimaps now support drag panning, keeping the main viewer centered under the pointer while dragging.

## [1.1.52] - 2026-05-21

### Fixed

- AI and Annotation minimaps now paint immediately from the already-loaded sidebar thumbnail before refreshing with the 2048px thumbnail.
- Minimap loads now ignore stale image callbacks when switching slides quickly.

## [1.1.51] - 2026-05-21

### Fixed

- Kept the high-resolution slide thumbnail visible under missing AI/Annotation viewer tiles until the actual tiles are ready.
- Delayed background overview tile preload a little longer so the thumbnail gets the first visible paint.

## [1.1.50] - 2026-05-21

### Changed

- AI and Annotation viewers now keep the slide loading overlay hidden during overview tile preload so the thumbnail fallback can show immediately.
- Overview tile preload now remains queued in the background instead of being cleared by render refreshes.
- Visible viewport tiles are promoted ahead of background overview preload when users zoom or navigate.

## [1.1.49] - 2026-05-20

### Changed

- Replaced Data Linkage sort text labels with compact CSS sort icons.

## [1.1.48] - 2026-05-20

### Fixed

- Added a Data Linkage client-side sorting fallback so row order changes immediately on header clicks.
- Exposed case last-activity timestamps for accurate Data Linkage sorting and hover details.
- Replaced symbolic sort arrows with ASCII labels to avoid encoding issues.

## [1.1.47] - 2026-05-20

### Fixed

- Removed the unused Additional conditions control from Data Linkage.
- Enabled server-backed sorting for the Data Linkage case table.

## [1.1.46] - 2026-05-20

### Changed

- Simplified the Data Linkage page title to a single label.
- Reduced linked image thumbnail clipping risk and added clearer selected image indicators.

## [1.1.45] - 2026-05-20

### Fixed

- Restored the shared top navigation on the Data Linkage page.
- Removed the gray preview background band from the Data Linkage viewer.

## [1.1.44] - 2026-05-20

### Changed

- Removed the one-quarter viewport cap from AI/Annotation viewer minimaps while keeping the initial minimap size fixed.

## [1.1.43] - 2026-05-20

### Fixed

- Fixed AI and Annotation viewer minimap display size so high-resolution thumbnails no longer enlarge the minimap.
- Capped minimap display and resize width to roughly one quarter of the viewport.

## [1.1.42] - 2026-05-20

### Fixed

- Changed upload duplicate handling to queue overwrite/skip decisions without blocking the remaining uploads.
- Added overwrite flow that deletes the existing original file, tiles, AI result cache, and DB slide record before re-uploading.
- Show unsupported/OpenSlide-invalid uploads as slide format errors and continue with the next file.

## [1.1.41] - 2026-05-20

### Fixed

- Added a static Data Linkage top navigation fallback so the main tabs remain visible even before shared header hydration.
- Added mouse wheel zoom, toolbar zoom controls, reset, and drag panning to the Data Linkage preview.

## [1.1.40] - 2026-05-20

### Fixed

- Added upload-popup token refresh keep-alive so long chunked uploads keep the access token current.
- Retried upload requests once after a forced refresh when a 401 occurs.

## [1.1.39] - 2026-05-20

### Changed

- Changed the default access token lifetime from 15 minutes to 360 minutes for on-premise workstation use.

## [1.1.38] - 2026-05-20

### Fixed

- Kept the shared top navigation visible on the Data Linkage page even if page data loading fails.
- Raised thumbnail-by-name and viewer thumbnail generation to 2048px minimum so Data Linkage previews and existing slide thumbnails use consistent resolution.

## [1.1.37] - 2026-05-20

### Added

- Added a Data Linkage page with project/hospital/sample filtering, case list, linked slide thumbnails, preview image, and shared clinical info editing.
- Added case-level clinical info API storage through `case_clinical_info` while keeping viewer slide clinical info synchronized.

## [1.1.36] - 2026-05-20

### Changed

- Changed clinical info storage from slide-level to case-level using the case name parsed from CODIPAI filenames.
- Shared clinical info across slides such as `CODIPAI-BRCA-SS-00192-I-KI-01.svs` and `CODIPAI-BRCA-SS-00192-I-ER-01.svs`.

## [1.1.35] - 2026-05-20

### Fixed

- Hardened Slide Information clinical score autosave by comparing actual field values on close.
- Updated AI slide list Clinical Info status immediately after a successful save.

## [1.1.34] - 2026-05-20

### Fixed

- Prevented thumbnail and preview image URLs from being requested with an empty media ticket.
- Delayed viewer fallback thumbnail/preview loading until a media ticket is ready.

## [1.1.33] - 2026-05-20

### Added

- Added AI slide list name search.
- Added Name, Clinical Info, and AI status columns to the AI slide list.

## [1.1.32] - 2026-05-20

### Added

- Added shared slide clinical score metadata fields to the AI and annotation Slide Information dialog.
- Added slide-level clinical metadata API endpoints and automatic save on dialog close/ESC.

## [1.1.31] - 2026-05-20

### Fixed

- Silenced Chrome DevTools `.well-known` probe requests with a 204 response.
- Suppressed benign Windows Proactor `ConnectionResetError` 10054 callback noise without hiding other asyncio errors.

## [1.1.30] - 2026-05-20

### Removed

- Removed the `Set AI Status` section from the AI slide context menu.

## [1.1.29] - 2026-05-20

### Changed

- Defaulted the annotation VS IHC panel to collapsed on first open while preserving the user's saved expanded/collapsed preference afterward.

## [1.1.28] - 2026-05-20

### Added

- Added a top-right minimizer to the annotation VS IHC panel so the panel controls can be collapsed without hiding the right sidebar.

## [1.1.27] - 2026-05-20

### Changed

- Temporarily disabled the Cell Annotation navigation item for non-admin users while keeping it available for admins.

## [1.1.26] - 2026-05-20

### Fixed

- Replaced the AI result class popup `Edit` text control with a fixed-width rename icon at the right edge so it no longer overlaps swatches or class labels.

## [1.1.25] - 2026-05-20

### Fixed

- Restored scanner/vendor and zoom/Mpp status badges inside the viewer toolbar instead of the header.
- Removed the duplicate legacy shortcut button group from the visible toolbar flow.

## [1.1.24] - 2026-05-20

### Fixed

- Replaced remaining corrupted viewer permission, upload, save/load, folder, VS IHC, and auto-AI UI strings in AI and annotation viewers with readable English labels.
- Cleaned damaged annotation viewer comments that were being preserved from the old encoding pass.

## [1.1.23] - 2026-05-20

### Fixed

- Render scanner/vendor and native MPP badges beside the slide title as well as in the toolbar so they remain visible when the toolbar right side is constrained.

## [1.1.22] - 2026-05-20

### Fixed

- Replaced corrupted AI runtime labels for running, cancel, start, fail, and completion states in AI and annotation viewers.

## [1.1.21] - 2026-05-20

### Fixed

- Restored scanner/vendor and native MPP badges in AI and annotation viewer toolbars by keeping the badge visible on narrow layouts.
- Added vendor, objective power, MPP, and physical-size metadata to the slide info endpoint.
- Broadened viewer metadata parsing to handle stored slide fields and OpenSlide property aliases.

## [1.1.20] - 2026-05-20

### Changed

- Replaced Annotation Class Management `Hide`/`Show` text buttons with eye visibility icons.

## [1.1.19] - 2026-05-20

### Changed

- Cleaned corrupted comments from the AI viewer module and replaced the file header with readable English documentation.

## [1.1.18] - 2026-05-20

### Fixed

- Restored Tissue/Cell Annotation page module loading by repairing corrupted UI strings in annotation workflow, class controls, cell edit popups, saved AI result loading, and breadcrumb rendering.
- Bumped the annotation viewer script cache key so browsers fetch the repaired module.

## [1.1.17] - 2026-05-20

### Fixed

- Restored AI page module loading by repairing corrupted syntax in viewer role controls, annotation panel callbacks, result list rendering, and slide list UI setup.
- Bumped the AI viewer app script cache key so browsers fetch the repaired project gate code.

## [1.1.16] - 2026-05-20

### Fixed

- Restored AI page project gate initialization after corrupted comment text swallowed the startup IIFE and slide-list drop initializer.

## [1.1.15] - 2026-05-20

### Fixed

- Restored the scanner/vendor and native MPP badge by reading scanner metadata from fallback slide fields and showing MPP details even when vendor is unknown.

## [1.1.14] - 2026-05-20

### Changed

- Reworked the AI viewer shortcut help to use the annotation-style Shortcuts modal with mouse icons and preview support.
- Updated AI Analysis help text to English across AI and annotation viewers.

## [1.1.13] - 2026-05-20

### Fixed

- Constrained the multi-cell edit popup width and wrapped its class-count summary to prevent oversized popups.

## [1.1.12] - 2026-05-20

### Fixed

- Hardened browser context-menu suppression for delayed contextmenu events after Alt+right-drag hidden Other selection.

## [1.1.11] - 2026-05-20

### Fixed

- Suppressed the browser context menu during Alt+right-click and Alt+right-drag viewer workflows.

## [1.1.10] - 2026-05-20

### Fixed

- Corrected saved AI edit cell counts to use visible result cells only, excluding hidden Other cells from saved metadata and normalized result JSON.
- User AI edit lists now re-sync older saved counts from the saved result JSON when opened.

## [1.1.9] - 2026-05-20

### Added

- Added draggable headers to cell edit, add, sticky class, and multi-cell edit popups.

## [1.1.8] - 2026-05-20

### Fixed

- Fixed undo/redo for promoted hidden Other cells so undo restores them to the hidden pool and redo promotes them again.

## [1.1.7] - 2026-05-20

### Fixed

- Stabilized the viewer crosshair cursor while Alt is held by adding a body-level cursor state.

## [1.1.6] - 2026-05-20

### Changed

- Changed sticky result-cell class picker shortcut from Shift+A to Alt+A.
- Moved the AI viewer UX help button next to the ruler tool with a toolbar separator.
- Hidden Other-cell lasso selection now applies the active model confidence threshold.

## [1.1.5] - 2026-05-20

### Fixed

- Restored the AI viewer top toolbar help button by un-hiding the help toolbar group.

## [1.1.4] - 2026-05-20

### Changed

- Changed hidden Other-cell selection from Ctrl+Alt drag to Alt+right-drag.
- Changed manual result-cell add from Shift+click to Alt+right-click.
- Alt now shows a crosshair cursor while held in the AI viewer.
- Added AI result editing shortcut notes to the viewer help dialog.

## [1.1.3] - 2026-05-20

### Added

- Added hidden Other-cell preservation for Quanti IHC and PD-L1 model results.
- Added Ctrl+Alt drag selection to promote hidden Other cells into visible editable result classes.

### Changed

- Hidden Other cells remain excluded from score calculations and visualization unless explicitly reclassified.
- Closing the Other-cell edit popup without assigning a class discards only the temporary selection.

## [1.1.2] - 2026-05-20

### Added

- Added VS IHC access to the top of Tissue Annotation and Cell Annotation right panels.

### Changed

- Annotation workspaces now show only the VS IHC AI tab instead of hiding the full AI panel.
- Annotation workspaces default the AI tab state to VS IHC.

## [1.1.1] - 2026-05-19

### Added

- Added a Project top-level tab and separated Annotation into Tissue and Cell annotation entry points.
- Added home dashboard slide distribution charts by project and hospital with segment hover tooltips.
- Added recent-slide page context so cards reopen the last used workspace.

### Changed

- Project open dialog now offers AI, Tissue Annotation, and Cell Annotation choices.
- Project table Default AI column now lists configured model names with model-family colors.
- Home Recent Slides cards now show workspace context instead of AI result badges.
- Removed the home summary stat cards and the Project table Due column.

### Fixed

- Fixed Annotation dropdown/header layering and hover behavior in project-gated screens.
- Fixed recent-slide cards incorrectly opening AI after annotation use.

## [1.1.0] - 2026-05-19

### Added

- Version management based on `main` version `1.0.1`; this dev release is calculated as `1.1.0`.
- Project-level management workflow.
- Separate AI and Annotation workspaces.
- Annotation class management, memo workflow, status workflow, and shortcut previews.
- Internal annotation storage under `backend/annotations`.
- Version metadata through `version.json`, `/api/version`, and shared header badge.

### Changed

- AI product naming aligned to Quanti HE, VS IHC, Quanti PD-L1, and Quanti IHC.
- Viewer entry flow now starts from project selection.
- Home dashboard reorganized around Project Management, Quick Actions, and Recent Slides.

### Notes

- This version is prepared on the `dev` branch before merging into `main`.
