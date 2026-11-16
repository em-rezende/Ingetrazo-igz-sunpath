# Changelog

All notable changes to **igz_sunpath** are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project follows [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-11-16

Feature release, tested with **IngeTrazo 0.5.8**. The plugin is now a
proper Python package: `igz_sunpath/__init__.py` exposes only `setup(app)`
and all runtime code lives under `igz_sunpath/core/`.

### Added

- **Sun Panel** — a dockable side panel (`app.add_panel`) with date/time
  sliders, north rotation, the location box, dome controls, animation
  controls, export settings and the FFmpeg status. Its widgets follow the
  dock width.
- **Sun animation** — **Play** and **Stop** toolbar buttons advance the
  current time in steps of 60, 30, 15, 10, 5 or 1 minute per frame until
  sunset, updating the overlay, the vector and the dome live.
- **Export Sequence / Video** — a new `ExportDialog` exports a **PNG image
  sequence** or an **MP4 video** (size, keep-aspect-ratio, include-dome
  and step-per-frame), with a preview of the animated viewport.
- **FFmpeg manager** — detects `ffmpeg` on `PATH` or in the plugin config
  folder, can **download and extract** it (`DependencyDialog`) and shows
  the dependency status in the panel.
- **New icons** for Play, Stop, Save/Export, Set Sun and the panel tab
  (dark and light variants).

### Changed

- **Source layout:** the former single-file module is split into
  `igz_sunpath/core/{state,toolbar,panel,overlay,overlay_paint,dome_geometry,solar_math,shadows,georef,scene_state,sun_animator,export_dialog,ffmpeg,capture,i18n_loader}.py`.
- `packaging/build_extension.py` now packages that layout (`core/`,
  `icons/`, `i18n/`, `screenshots/` and the docs) and writes a
  `dist/igz_sunpath.zip.sha256` sidecar next to the archive.
- The toolbar object name is now `igz_sunpath_toolbar`; the **Sun Panel**
  action is appended only when the host provides `app.add_panel`.
- Static and GUI smoke tests were rewritten for the package layout.

### Fixed

- **Removed `sys.path.insert(0, _HERE)` from `__init__.py`.** With the new
  `core/` folder it shadowed IngeTrazo's own `core` package, which broke
  `core.i18n` (interface always fell back to English) and could affect the
  host's `core.sun` import.
- **Chinese catalog:** `i18n/zh.json` was renamed to `i18n/zh-CN.json`
  (the code and the docs have always used the `zh-CN` language code) and
  its invalid JSON (a missing comma) was repaired. All seven catalogs now
  load and share the same keys.
- Added the four missing action-description strings to `en.json`.

## [1.0.0] — 2026-10-18

First public release, tested with **IngeTrazo 0.5.8**.

### Added

- **Sun Path toolbar** with nine actions: Shadows on/off, Sun Arrow,
  Sun Vector, Sun Dome, Set Sun Tool, Set Center, Calendar, Set Location
  and Save PNG.
- **On-screen compass overlay** (draggable) with cardinal points, the sun
  position, a live information panel and Date / Time sliders.
- **3D sun vector** with tip ball, dashed ground projection, hour label
  and Azimuth / Elevation labels at the origin.
- **3D solar dome** (domus solar) with twelve monthly arcs, a red arc for
  the selected day, hour marks, sunrise/sunset date labels, analemmas and
  a ground compass.
- **Clickable dome cells** that set date and time at once, plus a
  **TAB** semester filter (Jan–Jun / Jul–Dec).
- **Set Sun dialog**: date/time sliders, azimuth/elevation readout, north
  rotation, location box (map source, coordinates, native map picker and
  *Load map*) and dome options.
- **Set Center** picking through IngeTrazo's OSNAP engine, with a colour
  coded snap preview and ESC / right-click cancel.
- **Calendar dialog** with a `HH:mm` time editor.
- **PNG export** with white or transparent background, previewing the
  current viewport and the solar overlay.
- **Document persistence** of every toggle, the dome scale and origin,
  the display flags and the export preference (`igz_*` scene
  attributes); date/time use `scene.shadows` and north uses
  `scene.georef.north`.
- **Translations** in English, Português (Brasil), Español, Deutsch,
  Français, Italiano and 简体中文, with live language switching.
- **Themed icons** (dark and light SVG variants) and custom cursors.
- **Packaging and publishing tooling**: deterministic
  `packaging/build_extension.py`, Windows wrapper
  `packaging/build_extension.ps1`, a ready-to-submit catalog entry in
  `packaging/igz_sunpath.toml`, and static + GUI smoke tests.

### Changed

- The PNG export fallback now uses the system temporary folder instead of
  a hard-coded `C:\Temp`, so it also works on Linux and macOS.
- The white-background export renders the overlay exactly once, avoiding
  double compositing of its semi-transparent panels.
- The toolbar title now uses its own translation key (it previously
  reused "North").
- `DEBUG` is off by default in release builds.

### Fixed

- Added the missing `Center:`, `Sunpath` and detailed export-error strings
  to all seven translation catalogs.
- The package `__init__.py` now defines `setup(app)` explicitly, which is
  what the community catalog's static check looks for in a `.zip`
  extension.
