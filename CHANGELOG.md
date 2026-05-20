# Changelog

All notable changes to MeDIAuto Studio are tracked here.

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
