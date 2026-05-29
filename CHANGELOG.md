# Changelog

All notable changes to MeDIAuto Studio are tracked here.

## [1.1.167] - 2026-05-29

### Fixed

- Tighten the Cell Annotation Patch List summary-to-column spacing after removing the redundant status count line.

## [1.1.166] - 2026-05-29

### Fixed

- Restore Cell Annotation WSI patch-list panel sizing and remove the redundant patch status count line above the patch table.

## [1.1.165] - 2026-05-29

### Changed

- Separate the Cell Annotation patch-view right panel so annotation list and compact class management are primary, while patch list becomes a read-only secondary list without WSI Apply/Clear controls.

## [1.1.164] - 2026-05-29

### Fixed

- Render Cell Annotation slide-list workflow icons from live patch summaries instead of stale slide status fields.

## [1.1.163] - 2026-05-29

### Fixed

- Replace the legacy viewer Admin button placeholder text with a stable English label and refresh viewer script cache keys.

## [1.1.162] - 2026-05-29

### Fixed

- Normalize invalid user role values before rendering header badges and before applying frontend/backend role permissions.

## [1.1.161] - 2026-05-29

### Changed

- Change Cell Annotation Patch List Clear into an admin/doctor-only full patch deletion flow with a 5-second confirmation dialog.

## [1.1.160] - 2026-05-29

### Changed

- Keep Cell Annotation Patch List columns pinned while scrolling and add per-column sorting for patch, annotation, review, termination, and memo.

## [1.1.159] - 2026-05-29

### Changed

- Keep the Cell Annotation Patch List Apply/Clear controls pinned while scrolling and replace the Undo button with Clear for pending patch region drafts.

## [1.1.158] - 2026-05-29

### Fixed

- Keep Cell Annotation WSI required/exclude region drawing colors independent from the active cell class color.

## [1.1.157] - 2026-05-29

### Fixed

- Show rejected Cell Annotation review status as a distinct red state in patch view, WSI status summaries, and the left slide workflow indicators.

## [1.1.156] - 2026-05-29

### Changed

- Move Cell Annotation patch image/label/info export to a coalesced background task so patch status changes return immediately after the database update.

## [1.1.155] - 2026-05-29

### Fixed

- Return the updated Cell Annotation patch document after saving patch labels so the right panel, patch list, and slide workflow status refresh immediately.

## [1.1.154] - 2026-05-29

### Changed

- Split backend CPU-heavy work into dedicated web, viewer tile serving, tile generation, AI, Cell Annotation patch export, and upload executor pools.
- Added Windows thread affinity support and reduced AI internal I/O workers to avoid CPU oversubscription.

## [1.1.153] - 2026-05-29

### Fixed

- Keep pending Cell Annotation review and termination workflow indicators inactive until their prerequisite step has progressed.

## [1.1.152] - 2026-05-29

### Fixed

- Compact the annotation slide list workflow columns so filenames and status icons fit cleanly in the left panel.

## [1.1.151] - 2026-05-29

### Fixed

- Initialize Cell Annotation slide folders, labels, patches, and base info.json when a slide is opened, even before any patch is created.

## [1.1.150] - 2026-05-28

### Changed

- Show selected required/excluded patch counts and saved patch totals in the Cell Annotation patch apply progress UI.

## [1.1.149] - 2026-05-28

### Fixed

- Export Cell Annotation patch JPEGs through the same vendor-aware color pipeline used by the viewer.
- Regenerate exported patch JPEGs on Cell Annotation export so older raw-color patch files are corrected.

## [1.1.148] - 2026-05-28

### Changed

- Changed Cell Annotation patch list status colors so Required is blue and Running is orange.

## [1.1.147] - 2026-05-28

### Changed

- Changed the Cell Annotation project action from Classes to Setting.
- Added Cell Annotation AI assistance controls to the Cell Annotation project settings modal.
- Preserved project AI settings when updating project metadata through the shared API client.

## [1.1.146] - 2026-05-28

### Changed

- Renamed project Annotation AI assistance UI to Cell Annotation AI assistance.

## [1.1.145] - 2026-05-28

### Fixed

- Prevented Cell Annotation WSI status percent badges from clipping in the right panel.

## [1.1.144] - 2026-05-28

### Fixed

- Synchronize Cell Annotation automatic patch workflow status summaries to the left slide list.

## [1.1.143] - 2026-05-28

### Fixed

- Ensure Cell Annotation WSI status indicators render in the right panel even when status icon elements are not prebuilt.
- Apply read-only automatic percent summaries to WSI Annotation, Review, and Termination status steps.

## [1.1.142] - 2026-05-28

### Changed

- Made Cell Annotation WSI status read-only and automatically derived from required patch progress.
- Show WSI annotation state as before, running, or complete based on required patch count and completion percent.

## [1.1.141] - 2026-05-28

### Fixed

- Separated Cell Annotation Patch View labels from WSI required/exclude region selection.
- Preserved patch label geometry when saving patch cell annotations.

## [1.1.140] - 2026-05-28

### Fixed

- Changed Cell Annotation exclude regions to remove only currently saved patches that overlap the exclude shape.
- Prevented required-region Apply from replacing the whole patch list; it now adds/removes incrementally.

### Added

- Added a Patch List Apply progress bar for patch save, recompute, cleanup, and refresh steps.

## [1.1.139] - 2026-05-28

### Changed

- Start Cell Annotation WSI labeling assistance preload when a slide opens, even before required patches are applied.
- Reuse an in-flight labeling assistance preload per slide to avoid duplicate AI worker starts.

## [1.1.138] - 2026-05-28

### Changed

- Store Cell Annotation `WSI_Labeling_assistance.json` labels in compact bbox array format.
- Return WSI labeling assistance metadata without the full labels payload by default.
- Auto-compact existing object-label assistance files when they are read.

## [1.1.137] - 2026-05-28

### Fixed

- Show pending Cell Annotation required regions in green and exclude regions in red before Apply.
- Color saved Cell Annotation patch overlays by workflow status instead of keeping required patches green.

## [1.1.136] - 2026-05-28

### Fixed

- Regenerate Cell Annotation WSI labeling assistance when the current project Assist AI differs from the existing assistance file.
- Prevent point-only AI results from being saved as Cell Annotation WSI bbox assistance.

## [1.1.135] - 2026-05-28

### Changed

- Moved Cell Annotation required/exclude patch selection from the right panel to a toolbar eraser toggle.
- Changed Cell Annotation required patch overlays to green and exclude previews to red.

## [1.1.134] - 2026-05-28

### Changed

- Removed persisted `WSI_regions.json` files from the Cell Annotation workflow; WSI region selection is now only an Apply-time input.

## [1.1.133] - 2026-05-28

### Changed

- Changed Cell Annotation required/exclude WSI regions to one-time Apply inputs; patch tasks remain, but saved region overlays are cleared after Apply.
- Limited Cell Annotation region Undo to pending regions before Apply.

## [1.1.132] - 2026-05-28

### Fixed

- Prevented Cell Annotation patch refresh from hiding returned patch records because of local grid metadata mismatch.

## [1.1.131] - 2026-05-28

### Added

- Added separate project-level Cell Annotation class management stored under the Cell Annotation workspace.

### Fixed

- Stopped saving non-required Cell Annotation patches as patch tasks in API responses and `info.json`.
- Removed restore-on-click behavior for removed Cell Annotation patches.

## [1.1.130] - 2026-05-28

### Fixed

- Preserved YOLO model bbox coordinates in Quanti HE, Quanti PD-L1, and Quanti IHC result payloads.
- Changed Cell Annotation WSI labeling assistance to use model bboxes instead of fixed-size fallback boxes when available.
- Marked old point-only AI caches as stale so bbox-capable inference reruns and rewrites cache.
- Allowed existing point-based WSI labeling assistance files to be regenerated with model bboxes.

## [1.1.129] - 2026-05-28

### Fixed

- Prevented Cell Annotation from starting WSI labeling assistance when project Annotation AI is disabled.
- Added the frontend API helper for WSI labeling assistance project options.

## [1.1.128] - 2026-05-28

### Fixed

- Changed Cell Annotation patch workflow status to enter progress only after Apply creates at least one required patch.
- Hid Point and Cut tools from the Cell Annotation toolbar.
- Added pre-Apply pending patch visualization and pending patch counts for required and excluded regions.

## [1.1.127] - 2026-05-28

### Added

- Added project-level Annotation AI assistance settings with one selectable inherited or non-inherited model.
- Added Cell Annotation WSI labeling assistance APIs that run a separate assistance task and write bbox-format `WSI_Labeling_assistance.json`.

### Changed

- Stopped Cell Annotation patch export from overwriting `WSI_Labeling_assistance.json` with required-region data; required regions now export to `WSI_regions.json`.
- Bumped Home and Project page script cache keys.

## [1.1.126] - 2026-05-27

### Fixed

- Ensured the Admin Create User, Pending Approval, and Users role controls all include the Labeler role from one shared role option list.
- Bumped the Admin page script cache key.

## [1.1.125] - 2026-05-27

### Added

- Added Apply-based Cell Annotation patch selection with required and exclude region modes.
- Added Cell Annotation artifact export under `backend/cell_annotation/{slide_stem}` with patch JPEGs, patch labels, `info.json`, and `WSI_Labeling_assistance.json`.

### Changed

- Changed Cell Annotation patch identifiers to `patch_{num}` and renamed the right-panel list to Patch List.
- Hid Point and Cut tools on the Cell Annotation page.

## [1.1.124] - 2026-05-27

### Added

- Added the Labeler role to backend role validation and Admin user management.
- Allowed Labeler users to run AI analysis while blocking AI result save/load and detection-result editing.

### Changed

- Restricted Labeler project management permissions.
- Limited Tissue Annotation status changes for Labeler users to the Annotation step before review or termination starts.
- Limited Cell Annotation Labeler users to patch-level annotation work while keeping WSI-level setup immutable.

## [1.1.123] - 2026-05-27

### Fixed

- Prevented Cell Annotation status labels and completion percentage from overlapping in the right panel.
- Preserved the running-state indicator while showing WSI-level patch completion percentage.

## [1.1.122] - 2026-05-27

### Fixed

- Connected the Cell Annotation Patch View status panel to the selected patch workflow state.

## [1.1.121] - 2026-05-27

### Fixed

- Show selected patch workflow status in the Annotation Status panel while Cell Annotation Patch View is active.

## [1.1.120] - 2026-05-27

### Added

- Show WSI-level Cell Annotation completion as a percentage in the Annotation status panel.
- Made Required Patches Anno., Review, and Term. columns editable from the patch list.

## [1.1.119] - 2026-05-27

### Changed

- Fixed Cell Annotation grid line width at 1px and removed its display control.
- Changed Cell Annotation patch overlay defaults to 1px border and 5% fill opacity.

## [1.1.118] - 2026-05-27

### Fixed

- Refitted Cell Annotation Patch View when selecting a different patch from the Required Patches list.

## [1.1.117] - 2026-05-27

### Added

- Added Cell Annotation patch overlay controls for grid line width, patch border width, and patch fill opacity.

### Changed

- Hid the AI Progress panel in Cell Annotation patch workflow mode.

## [1.1.116] - 2026-05-27

### Fixed

- Allowed manually removed Cell Annotation patches to be restored from WSI click or the patch context menu.

## [1.1.115] - 2026-05-27

### Fixed

- Stopped regular WSI patch selection from fitting the viewer to the patch.
- Kept the selected WSI patch synchronized and visible in the Required Patches panel.

## [1.1.114] - 2026-05-27

### Changed

- Changed the Cell Annotation required patch list to Patch, Anno., Review, Term., and Memo columns.
- Replaced the patch memo prompt with a memo dialog that supports current memo, answers, and previous memo history.

## [1.1.113] - 2026-05-27

### Added

- Added right-click Cell Annotation patch actions for patch memo editing and removing a patch from the required list.

## [1.1.112] - 2026-05-27

### Changed

- Hid the Cell Annotation required-region polygon overlay while keeping patch generation and undo behavior.

## [1.1.111] - 2026-05-27

### Changed

- Removed the in-canvas Patch View label from Cell Annotation Patch View.
- Allowed Patch View panning across the slide while keeping the toolbar Fit action focused on the selected patch.

## [1.1.110] - 2026-05-27

### Fixed

- Separated Tissue Annotation and Cell Annotation slide workflow statuses.
- Cell Annotation now stores status in its own slide field instead of sharing Tissue Annotation status.

## [1.1.109] - 2026-05-27

### Changed

- Changed Cell Annotation patch IDs to use slide coordinates, such as px_3072_py_4096.
- Updated the required patch list to show Annotation, Review, and Termination workflow columns.

## [1.1.108] - 2026-05-27

### Fixed

- Prevented Patch View clicks and double-clicks from switching to other WSI patches.
- Constrained viewer pan and zoom to the selected patch while Patch View is active.

## [1.1.107] - 2026-05-27

### Changed

- Moved the Cell Annotation Patch View / WSI View toggle to the viewer toolbar.
- Hid required-region, grid, and patch status overlays while Patch View is active.
- Renamed the Hamamatsu NDP toggle label to NDP Color.

## [1.1.106] - 2026-05-27

### Added

- Added Cell Annotation patch focus view from double-clicking a required patch.
- Added a Patch View / WSI View toggle and P shortcut that restore the previous WSI viewport without reloading the slide.

## [1.1.105] - 2026-05-27

### Changed

- Cell Annotation now automatically marks the Annotation workflow step as in progress after a WSI required region is drawn.

## [1.1.104] - 2026-05-27

### Fixed

- Hid not-required Cell Annotation patch overlays so inactive patches do not leave gray grid remnants.
- Filtered stale patch status records whose saved coordinates do not match the current 512um grid.

## [1.1.103] - 2026-05-27

### Added

- Added Cell Annotation required-region undo from the required patch panel.
- Added Ctrl+Z handling to remove the latest required region and recompute patch statuses.

## [1.1.102] - 2026-05-26

### Changed

- Updated Cell Annotation patch grid sizing from 256um to 512um physical patches at the 0.5um/px target.
- Replaced the Cell Annotation annotation list area with a required patch task list that shows each patch status.
- Hid tissue-style annotation class/style controls on the Cell Annotation patch workflow page.

## [1.1.101] - 2026-05-26

### Fixed

- Replaced corrupted Admin page labels and broken JavaScript strings with clean English UI text.
- Bumped the Admin script cache key so the repaired page loads immediately.

## [1.1.100] - 2026-05-26

### Added

- Added a separate patch-based Cell Annotation workflow foundation with deterministic patch IDs, required-region storage, patch status APIs, and patch cell storage.
- Added dedicated frontend layers for patch grid drawing, patch status overlays, WSI-level required regions, and patch cell editing.

### Changed

- Added a minimal TileViewer overlay-layer hook so Cell Annotation can draw patch workflow overlays without coupling the logic into the core viewer.

## [1.1.99] - 2026-05-26

### Changed

- Removed the annotation workflow connector separators so only step buttons and their state icons remain.

## [1.1.98] - 2026-05-26

### Changed

- Moved annotation workflow status icons outside each step button so the button label remains clean.
- Restored workflow connectors to simple separators between steps.

## [1.1.97] - 2026-05-26

### Fixed

- Enabled the VS IHC split-view control after virtual staining results load on annotation pages.
- Passed VS ROI polygons through the annotation-page overlay setup to match the AI viewer behavior.

## [1.1.96] - 2026-05-26

### Changed

- Replaced annotation workflow text status labels with icon states: green check for done, orange in-progress marker for running, blue dash for current, and yellow dash for pending.
- Bumped annotation page cache keys for the updated workflow controls.

## [1.1.95] - 2026-05-26

### Fixed

- Kept the VS IHC 1.1.78 viewer behavior and added a backend fallback so VS tile/image requests reopen slides from uploads when they are not currently held by the slide manager.
- Prevented VS IHC media endpoints from returning 404 only because the slide was evicted from memory.

## [1.1.94] - 2026-05-26

### Fixed

- Restored VS IHC backend and viewer tile behavior to the 1.1.78 implementation.
- Removed the later VS tile manifest/request-gating changes that caused overlay rendering regressions.
- Bumped frontend module cache keys so the restored viewer code loads immediately.

## [1.1.93] - 2026-05-26

### Changed

- Removed Korean and replacement characters from backend and frontend source files to avoid PowerShell encoding corruption.
- Kept runtime syntax intact by using direct Unicode-range replacement instead of shell-encoded Korean replacement maps.

## [1.1.92] - 2026-05-26

### Fixed

- Added a VS IHC tile manifest endpoint so the viewer can check the actual cached tile coordinates before requesting overlay tiles.
- Blocked VS IHC overlay tile loading until the manifest is available, preventing low-zoom requests for nonexistent sparse pyramid tiles.
- Bumped frontend module cache keys so the manifest-based tile filtering is loaded immediately.

## [1.1.91] - 2026-05-26

### Fixed

- VS IHC cached results now include the actual tile keys present on disk.
- The viewer skips VS IHC tile URLs that are not present in the cached pyramid, avoiding noisy 404 requests.
- Bumped frontend module cache keys so the updated VS tile filtering is loaded immediately.

## [1.1.90] - 2026-05-26

### Fixed

- Restored sparse VS IHC overlay behavior from 1.1.78 by not returning blank JPEGs for missing overlay tiles.
- Missing VS IHC tiles now remain undrawn instead of covering the slide with white fallback tiles.

## [1.1.89] - 2026-05-26

### Fixed

- VS IHC tile serving now resolves slide paths from the slide database when the in-memory slide handle is missing.
- Cached VS IHC tiles and blank-tile fallbacks no longer depend on the slide staying open in `slide_manager`.

## [1.1.88] - 2026-05-22

### Fixed

- Added backend fallback for missing VS IHC pyramid tiles.
- Missing VS IHC parent tiles are rebuilt from child tiles when possible.
- Empty VS IHC areas now return a cached blank JPEG instead of noisy 404 responses.

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
