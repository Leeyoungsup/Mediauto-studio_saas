# Changelog

All notable changes to MeDIAuto Studio are tracked here.

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
