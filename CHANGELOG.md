# Changelog

All notable changes to **igz_sunpath** are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project follows [Semantic Versioning](https://semver.org/).

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
