# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ezequiel M. Rezende
"""GUI smoke test — optional, skipped when PySide6 is not installed.

It builds a fake IngeTrazo main window (a QMainWindow with a viewport
widget and the two scene dataclasses the plugin reads), calls ``setup(app)``
and exercises the toolbar, the solar math, the overlay painter, the dialogs
and the PNG export.  It runs offscreen::

    python -m unittest discover -s tests -v

On Windows, IngeTrazo bundles PySide6 inside its application folder, so use
a Python that can import PySide6 (for example a QGIS/OSGeo Python).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QDate, QTime
    from PySide6.QtGui import QVector3D
    from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QWidget
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise unittest.SkipTest(f"PySide6 is not available: {exc}")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

import igz_sunpath as package  # noqa: E402

mod = package.igz_sunpath

EXPECTED_ACTIONS = (
    "Shadows on/off", "Sun Arrow", "Sun Vector", "Sun Dome",
    "Set Sun Tool", "Set Center", "Calendar", "Set Location", "Save PNG",
)


class Shadows:
    enabled = True
    month = 3
    day = 21
    hour = 12
    minute = 0
    darkness = 0.5


class Georef:
    lat = -19.9167
    lon = -43.9345
    north = 0.0


class Scene:
    def __init__(self):
        self.shadows = Shadows()
        self.georef = Georef()


class Viewport(QWidget):
    """A plain QWidget with the two viewport methods the plugin uses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = Scene()
        self.resize(800, 600)

    def world_to_pixel(self, v):  # noqa: N802 - mirrors the host API
        if not isinstance(v, QVector3D):
            v = QVector3D(v)
        return (400.0 + float(v.x()) * 20.0, 300.0 - float(v.z()) * 20.0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.resize(1000, 700)


class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.win = MainWindow()
        cls.win.show()
        cls.app.processEvents()
        mod.setup(SimpleNamespace(main_window=cls.win))
        cls.app.processEvents()
        cls.overlay = mod._ensure_overlay(cls.win)
        mod._SUN_DOME_ACTIVE = True
        mod._SUN_VECTOR_ACTIVE = True
        mod._OVERLAY_VISIBLE = True
        mod._sync_overlay_visibility(cls.win)
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        for timer_name in ("_SCENE_TIMER", "_LANG_TIMER"):
            timer = getattr(mod, timer_name)
            if timer is not None:
                timer.stop()
                setattr(mod, timer_name, None)
        if mod._OVERLAY is not None:
            mod._OVERLAY.close()
            mod._OVERLAY.deleteLater()
            mod._OVERLAY = None
        cls.win.close()
        cls.win.deleteLater()
        cls.app.processEvents()

    def test_toolbar_and_actions(self):
        toolbars = [tb for tb in self.win.findChildren(QToolBar)
                    if tb.objectName() == "igz_sunpath"]
        self.assertEqual(len(toolbars), 1)
        texts = [action.text() for action in toolbars[0].actions()
                 if not action.isSeparator()]
        self.assertEqual(tuple(texts), EXPECTED_ACTIONS)

    def test_solar_math(self):
        sh = self.win.viewport.scene.shadows
        sh.month, sh.day, sh.hour, sh.minute = 3, 21, 12, 0
        az, el = mod._solar_position(sh, -19.9167)
        self.assertGreater(el, 60.0)
        self.assertLess(el, 80.0)
        self.assertTrue(0.0 <= az <= 360.0)
        sh.hour, sh.minute = 0, 0
        _, el_night = mod._solar_position(sh, -19.9167)
        self.assertLess(el_night, 0.0)

    def test_dome_cache(self):
        cache = mod._build_dome_cache(5.0, -19.9167, 3, 21)
        self.assertGreaterEqual(len(cache["meridians"]), 12)
        self.assertEqual(len(cache["analemas"]), 13)
        self.assertGreater(len(cache["cells"]), 0)
        special = [m for m in cache["meridians"] if m["special"]]
        self.assertEqual(len(special), 1)

    def test_overlay_paints(self):
        self.assertIsNotNone(self.overlay)
        pixmap = self.overlay.grab()
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), self.win.viewport.width())

    def test_export_png_white_and_transparent(self):
        with tempfile.TemporaryDirectory() as tmp:
            for transparent in (False, True):
                mod._EXPORT_TRANSPARENT_BG = transparent
                path = Path(tmp) / f"export_{transparent}.png"
                self.assertTrue(
                    mod._capture_viewport_to_png(self.win, str(path)))
                self.assertTrue(path.is_file())
                self.assertTrue(
                    path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_dialogs_construct(self):
        dialogs = [
            mod._SetSunDialog(self.win),
            mod._ExportPngDialog(self.win),
            mod._ShadowsCalendarDialog(self.win, QDate(2026, 3, 21),
                                       QTime(12, 0)),
        ]
        try:
            for dialog in dialogs:
                self.assertTrue(dialog.windowTitle())
                self.assertGreater(dialog.sizeHint().width(), 0)
        finally:
            for dialog in dialogs:
                dialog.close()
                dialog.deleteLater()
            self.app.processEvents()

    def test_state_round_trip(self):
        mod._SUN_DOME_ACTIVE = True
        mod._SUN_VECTOR_ACTIVE = True
        mod._OVERLAY_VISIBLE = True
        mod._DOME_DIAGRAM_SCALE = 2.5
        mod._DOME_SHOW_ANALEMAS = False
        mod._EXPORT_TRANSPARENT_BG = True
        mod._DOME_CENTER_XYZ = QVector3D(1.0, 2.0, 3.0)
        mod._save_state_to_scene(self.win)

        mod._SUN_DOME_ACTIVE = False
        mod._SUN_VECTOR_ACTIVE = False
        mod._OVERLAY_VISIBLE = False
        mod._DOME_DIAGRAM_SCALE = 1.0
        mod._DOME_SHOW_ANALEMAS = True
        mod._EXPORT_TRANSPARENT_BG = False
        mod._DOME_CENTER_XYZ = None
        mod._load_state_from_scene(self.win)

        self.assertTrue(mod._SUN_DOME_ACTIVE)
        self.assertTrue(mod._SUN_VECTOR_ACTIVE)
        self.assertTrue(mod._OVERLAY_VISIBLE)
        self.assertAlmostEqual(mod._DOME_DIAGRAM_SCALE, 2.5)
        self.assertFalse(mod._DOME_SHOW_ANALEMAS)
        self.assertTrue(mod._EXPORT_TRANSPARENT_BG)
        self.assertAlmostEqual(mod._DOME_CENTER_XYZ.x(), 1.0)
        self.assertAlmostEqual(mod._DOME_CENTER_XYZ.z(), 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

