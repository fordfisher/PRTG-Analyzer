# Changelog

All notable changes to PyPRTG_CLA are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.5.4] — 2026-03-11

### Added

- In-app update flow: check for updates from GitHub Releases, download and extract new version, restart into new EXE.
- Update overlay in the UI with "Update now" and "Reload page"; automatic page reload when the new app is back.
- `build-and-release.ps1` script to build EXE, copy `apply-update.bat` to folder root, and create versioned zip for GitHub release.
- Automated tests for apply-update (download, extract, launch via cmd start) in `tests/test_update.py`.

### Changed

- New version is launched via `cmd start` so the process is detached and gets its own window; batch script only performs wait and taskkill.
- Apply-update copies `apply-update.bat` from `_internal` to folder root if missing in the extracted zip (backward compatible with older zip layout).
- "Folder already exists" error now includes the full path so users can locate or remove the folder.

### Fixed

- Updater now correctly starts the new app after download and extract (previously the new EXE was not launched).
- Release zip layout: `apply-update.bat` is at the root of the extracted folder so the in-app updater finds it.

---

## [1.5.3] — 2026-03-11

- Release with updater fix (cmd start launch) for testing the update path from 1.5.3 to 1.5.4.

## [1.5.2] — 2026-03-11

- Version used for updater validation; UI overlay for update notifications.

## [1.5] — 2026-03

- Stable release with responsive UI and update mechanism.

## [1.4] / [1.41]

- Check for updates button; overlay and layout improvements.

## [1.3] and earlier

- Core analysis, Status Data support, export, timeline, health score, and rules engine.

[1.5.4]: https://github.com/fordfisher/PRTG-Analyzer/releases/tag/v1.5.4
[1.5.3]: https://github.com/fordfisher/PRTG-Analyzer/releases/tag/v1.5.3
[1.5.2]: https://github.com/fordfisher/PRTG-Analyzer/releases/tag/v1.5.2
