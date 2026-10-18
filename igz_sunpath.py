# =========================================================================
# Copyright (C) 2026 IngeTrazo Contributors / Ezequiel M. Rezende
# GPL-3.0-or-later — see LICENSE
# =========================================================================
# Extension: igz_sunpath
# Version: 1.0.0
# =========================================================================
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import traceback

from PySide6.QtCore import (
    Qt, QDate, QTime, QTimer, QPoint, QPointF, QRectF, QEvent, QObject,
    QStandardPaths, QDateTime,
)
from PySide6.QtGui import (
    QAction, QIcon, QPainter, QPen, QColor, QBrush, QPalette,
    QVector3D, QCursor, QPixmap, QPolygonF, QImage,
)
from PySide6.QtWidgets import (
    QToolBar, QMessageBox, QSizePolicy, QLineEdit,
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QWidget, QFrame, QGroupBox, QCheckBox, QDoubleSpinBox,
    QComboBox, QApplication, QCalendarWidget, QTimeEdit, QFileDialog,
)

__version__ = "1.0.0"

# Set to True only while developing: it prints diagnostics to stderr.
DEBUG = False


def _log(msg: str) -> None:
    if DEBUG:
        print(f"[igz_sunpath] {msg}", file=sys.stderr, flush=True)


# =========================================================================
# 1. i18n
# =========================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_I18N_DIR = os.path.join(_HERE, "i18n")
_TRANSLATIONS_CACHE = {}

try:
    from core.i18n import current_language as _it_language
except Exception:
    def _it_language():
        return "en"


def _load_translation_file(lang_code: str) -> dict:
    if lang_code in _TRANSLATIONS_CACHE:
        return _TRANSLATIONS_CACHE[lang_code]
    file_path = os.path.join(_I18N_DIR, f"{lang_code}.json")
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _TRANSLATIONS_CACHE[lang_code] = data
                return data
        except Exception:
            traceback.print_exc()
    _TRANSLATIONS_CACHE[lang_code] = {}
    return {}


def _t(text: str) -> str:
    lang = _it_language()
    trans = _load_translation_file(lang)
    if text in trans:
        return trans[text]
    if lang != "en":
        en = _load_translation_file("en")
        if text in en:
            return en[text]
    return text


_LOCAL_MONTHS = {
    "en":    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es":    ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"],
    "id":    ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
    "it":    ["gen", "feb", "mar", "apr", "mag", "giu",
              "lug", "ago", "set", "ott", "nov", "dic"],
    "pt-BR": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
              "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    "de":    ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
              "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    "fr":    ["jan", "fév", "mar", "avr", "mai", "jun",
              "jul", "aoû", "sep", "oct", "nov", "déc"],
    "zh-CN": ["1月", "2月", "3月", "4月", "5月", "6月",
              "7月", "8月", "9月", "10月", "11月", "12月"],
}


def _months():
    return _LOCAL_MONTHS.get(_it_language(), _LOCAL_MONTHS["en"])


# =========================================================================
# 2. Constants
# =========================================================================
_LATITUDE_DEG = -19.9167
_LONGITUDE_DEG = -43.9345

_SUN_VECTOR_ACTIVE = False
_SUN_DOME_ACTIVE = False
_NORTH_ROTATION_DEG = 0.0
_DOME_CENTER_XYZ = None

_PICKING_CENTER = False

_HOVER_CELL_IDX = -1
_HOVER_CURSOR_APPLIED = False

_DOME_BASE_RADIUS = 5.0
_DOME_DIAGRAM_SCALE = 1.0
_DOME_SCALE_MIN = 0.20          # 20%  (limite inferior)
_DOME_SCALE_MAX = 20.0          # 2000% (limite superior)
_DOME_SCALE_SLIDER_MIN = 0      # posição mínima do QSlider
_DOME_SCALE_SLIDER_MAX = 1000   # posição máxima do QSlider (resolução interna)
_DOME_HOUR_STEP_MIN = 15
_DOME_MARKED_HOURS = tuple(range(5, 20))
_DOME_COMPASS_STEP_DEG = 10
_CELL_HOURS = tuple(range(5, 20))

_ANALEMA_HOURS = tuple(range(6, 19))
_ANALEMA_DAY_STEP = 5

_DOME_SHOW_ANALEMAS = True
_DOME_SHOW_HOUR_LABELS = True
_DOME_SHOW_DATE_LABELS = True
_DOME_SHOW_COMPASS = True

_USE_OSNAP_FOR_CENTER = True
_DIALOG_HIDDEN_FOR_PICKING = False

_MAP_SOURCES = [
    ("Esri World Imagery (satellite)", "esri_imagery"),
    ("Sentinel-2 cloudless (EOX)",     "s2cloudless"),
    ("OpenStreetMap",                  "osm"),
]
_SELECTED_MAP_SID = "esri_imagery"
_LOAD_MAP_TOO = False

_EXPORT_TRANSPARENT_BG = False

_USE_SECOND_HALF_YEAR = False
_TAB_SHORTCUT = None


def _dome_radius():
    return _DOME_BASE_RADIUS * _DOME_DIAGRAM_SCALE


# =========================================================================
# 3. Icons / cursors
# =========================================================================
def _find_icons_folder():
    c = os.path.join(_HERE, "icons")
    return c if os.path.isdir(c) else None


_ICONS_DIR = _find_icons_folder()


def _discover_main_window():
    try:
        qapp = QApplication.instance()
        if qapp is None:
            return None
        for w in qapp.topLevelWidgets():
            if type(w).__name__ == "MainWindow":
                return w
        for w in qapp.topLevelWidgets():
            if hasattr(w, "addToolBar"):
                return w
    except Exception:
        traceback.print_exc()
    return None


def _load_themed_icon(base_name: str, main_window) -> QIcon:
    if not _ICONS_DIR:
        return QIcon()
    is_dark = True
    try:
        if main_window is not None:
            bg = main_window.palette().color(QPalette.Window)
            is_dark = bg.lightness() < 128
    except Exception:
        pass
    if not is_dark:
        p = os.path.join(_ICONS_DIR, f"{base_name}_light.svg")
        if os.path.isfile(p):
            return QIcon(p)
    p = os.path.join(_ICONS_DIR, f"{base_name}.svg")
    if os.path.isfile(p):
        return QIcon(p)
    return QIcon()


def _load_custom_cursor(base_name: str, main_window) -> QCursor:
    if not _ICONS_DIR:
        return QCursor(Qt.CrossCursor)
    is_dark = True
    try:
        if main_window is not None:
            bg = main_window.palette().color(QPalette.Window)
            is_dark = bg.lightness() < 128
    except Exception:
        pass
    candidates = []
    if not is_dark:
        candidates.append(os.path.join(_ICONS_DIR, f"{base_name}_light.svg"))
    candidates.append(os.path.join(_ICONS_DIR, f"{base_name}.svg"))
    for path in candidates:
        if not (path and os.path.isfile(path)):
            continue
        try:
            pm = QPixmap(path)
            if pm.isNull():
                try:
                    from PySide6.QtSvg import QSvgRenderer
                    r = QSvgRenderer(path)
                    if r.isValid():
                        pm = QPixmap(24, 24)
                        pm.fill(Qt.transparent)
                        p = QPainter(pm)
                        try:
                            r.render(p)
                        finally:
                            p.end()
                except Exception:
                    traceback.print_exc()
            if not pm.isNull():
                s = pm.scaled(24, 24, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
                return QCursor(s, 12, 12)
        except Exception:
            traceback.print_exc()
    return QCursor(Qt.CrossCursor)


# =========================================================================
# 4. Access helpers
# =========================================================================
def _get_scene(main_window):
    vp = getattr(main_window, "viewport", None)
    return getattr(vp, "scene", None) if vp is not None else None


def _get_viewport(main_window):
    return getattr(main_window, "viewport", None)


def _get_shadows(main_window):
    sc = _get_scene(main_window)
    return getattr(sc, "shadows", None) if sc is not None else None


def _repaint(main_window) -> None:
    vp = _get_viewport(main_window)
    if vp is not None and hasattr(vp, "update"):
        vp.update()
    global _OVERLAY
    if _OVERLAY is not None and _OVERLAY.isVisible():
        _OVERLAY.update()


def _scene_get_attr(scene, key, default=None):
    if scene is None:
        return default
    for h in ("attrs", "attributes", "meta"):
        d = getattr(scene, h, None)
        if isinstance(d, dict) and key in d:
            return d[key]
    return getattr(scene, key, default)


def _scene_set_attr(scene, key, value) -> bool:
    if scene is None:
        return False
    for h in ("attrs", "attributes", "meta"):
        d = getattr(scene, h, None)
        if isinstance(d, dict):
            d[key] = value
            return True
    try:
        setattr(scene, key, value)
        return True
    except Exception:
        return False


# =========================================================================
# 5. Georef / North rotation
# =========================================================================
def _read_georef_from_scene(scene):
    if scene is None:
        return None
    gr = getattr(scene, "georef", None)
    if gr is None:
        return None
    lat = lon = None
    for n in ("lat", "latitude", "lat_deg"):
        v = getattr(gr, n, None)
        if isinstance(v, (int, float)):
            lat = float(v); break
    for n in ("lon", "longitude", "lng", "lon_deg"):
        v = getattr(gr, n, None)
        if isinstance(v, (int, float)):
            lon = float(v); break
    if lat is not None and lon is not None:
        return (lat, lon)
    return None


def _get_georef(main_window):
    # The constants are only a fallback for documents without a georef.
    r = _read_georef_from_scene(_get_scene(main_window))
    return r if r is not None else (_LATITUDE_DEG, _LONGITUDE_DEG)


def _rotate_north(x, y, z):
    if _NORTH_ROTATION_DEG == 0.0:
        return (x, y, z)
    a = math.radians(-_NORTH_ROTATION_DEG)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca, z)


def _read_north_rotation(scene):
    if scene is None:
        return 0.0
    gr = getattr(scene, "georef", None)
    if gr is not None and hasattr(gr, "north"):
        try:
            return float(gr.north)
        except Exception:
            pass
    try:
        return float(_scene_get_attr(scene, "north_rotation_deg", 0.0))
    except Exception:
        return 0.0


# =========================================================================
# 6. Shadows helpers
# =========================================================================
def _shadows_set_date(sh, month: int, day: int) -> None:
    sh.month = int(month)
    sh.day = int(day)
    sh.enabled = True


def _shadows_set_time(sh, hour: int, minute: int) -> None:
    sh.hour = int(hour)
    sh.minute = int(minute)
    sh.enabled = True


# =========================================================================
# 7. Solar math
# =========================================================================
def _day_of_year_to_date(day_of_year: int):
    d = QDate(2026, 1, 1).addDays(max(1, min(365, day_of_year)) - 1)
    return d.month(), d.day()


def _solar_declination_deg(day_of_year: int) -> float:
    return 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))


def _equation_of_time_min(day_of_year: int) -> float:
    B = math.radians(360.0 * (day_of_year - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def _solar_position(sh, latitude_deg: float = _LATITUDE_DEG):
    if sh is None:
        return 0.0, 0.0
    try:
        d = QDate(2026, int(sh.month), int(sh.day))
        doy = d.dayOfYear()
        decl = math.radians(_solar_declination_deg(doy))
        hour_f = float(sh.hour) + float(sh.minute) / 60.0
        hour_f += _equation_of_time_min(doy) / 60.0
        H = math.radians((hour_f - 12.0) * 15.0)
        lat = math.radians(latitude_deg)
        sin_elev = (math.sin(lat) * math.sin(decl)
                    + math.cos(lat) * math.cos(decl) * math.cos(H))
        sin_elev = max(-1.0, min(1.0, sin_elev))
        el_deg = math.degrees(math.asin(sin_elev))
        y = math.sin(H)
        x = math.cos(H) * math.sin(lat) - math.tan(decl) * math.cos(lat)
        az = (math.degrees(math.atan2(y, x)) + 180.0) % 360.0
        if el_deg > 89.0:
            az = 0.0
        return az, el_deg
    except Exception:
        traceback.print_exc()
        return 0.0, 0.0


# =========================================================================
# 8. Dome geometry
# =========================================================================
_DOME_CACHE = None


def _get_dome_center() -> QVector3D:
    global _DOME_CENTER_XYZ
    return _DOME_CENTER_XYZ if _DOME_CENTER_XYZ is not None else QVector3D(0, 0, 0)


def _dome_point(az_deg: float, el_deg: float, radius: float):
    ar, er = math.radians(az_deg), math.radians(el_deg)
    x = radius * math.cos(er) * math.sin(ar)
    y = radius * math.cos(er) * math.cos(ar)
    z = radius * math.sin(er)
    rx, ry, rz = _rotate_north(x, y, z)
    c = _get_dome_center()
    return (rx + c.x(), ry + c.y(), rz + c.z())


def _sunrise_sunset_points(date_month_day, radius, lat_deg):
    m, d = date_month_day

    def _el_at(mn):
        h, mi = mn // 60, mn % 60
        class _S: pass
        s = _S(); s.month = m; s.day = d; s.hour = h; s.minute = mi
        try:
            return _solar_position(s, lat_deg)
        except Exception:
            return None

    step = 2
    prev = None
    sr_az = None
    ss_az = None
    for mn in range(0, 24 * 60 + 1, step):
        cur = _el_at(mn)
        if cur is None:
            prev = None; continue
        if prev is not None:
            az0, el0 = prev; az1, el1 = cur
            if el0 < 0 <= el1 and sr_az is None:
                t = -el0 / (el1 - el0) if (el1 - el0) else 0.0
                sr_az = (az0 + t * (az1 - az0)) % 360.0
            if el0 >= 0 > el1 and ss_az is None:
                t = el0 / (el0 - el1) if (el0 - el1) else 0.0
                ss_az = (az0 + t * (az1 - az0)) % 360.0
        prev = cur
        if sr_az is not None and ss_az is not None:
            break
    if sr_az is None or ss_az is None:
        return None
    ar_sr, ar_ss = math.radians(sr_az), math.radians(ss_az)
    sr = (radius * math.sin(ar_sr), radius * math.cos(ar_sr), 0.0)
    ss = (radius * math.sin(ar_ss), radius * math.cos(ar_ss), 0.0)
    sr = _rotate_north(*sr); ss = _rotate_north(*ss)
    c = _get_dome_center()
    return ((sr[0] + c.x(), sr[1] + c.y(), sr[2] + c.z()),
            (ss[0] + c.x(), ss[1] + c.y(), ss[2] + c.z()))


def _build_analemas_cache(radius, lat_deg):
    analemas = []
    for h in _ANALEMA_HOURS:
        pts = []
        for doy in range(1, 366, _ANALEMA_DAY_STEP):
            d = QDate(2026, 1, 1).addDays(doy - 1)
            class _S: pass
            s = _S(); s.month = d.month(); s.day = d.day()
            s.hour = h; s.minute = 0
            try:
                az, el = _solar_position(s, lat_deg)
            except Exception:
                continue
            if el <= 0.0:
                continue
            pts.append(_dome_point(az, el, radius))
        if len(pts) >= 2:
            pts.append(pts[0])
        analemas.append({"hour": h, "pts": pts})
    return analemas


def _point_at_hour(meridian_pts, meridian_marcados, hour):
    for entry in meridian_marcados:
        x, y, z, h = entry
        if int(h) == int(hour):
            return (x, y, z)
    return None


def _build_cells(meridians, radius, lat_deg):
    cells = []
    global _USE_SECOND_HALF_YEAR
    if _USE_SECOND_HALF_YEAR:
        allowed_months = {7, 8, 9, 10, 11, 12}
    else:
        allowed_months = {1, 2, 3, 4, 5, 6}

    monthly = []
    for idx, md in enumerate(meridians):
        if md.get("special"):
            continue
        m = md.get("month")
        if int(md["label"].split("/")[0]) == 15 and m in allowed_months:
            monthly.append((m, 15, idx))

    monthly.sort(key=lambda t: t[0])
    if len(monthly) < 2:
        return cells

    hours = list(_CELL_HOURS)
    for k in range(len(monthly) - 1):
        m0, d0, idx0 = monthly[k]
        m1, d1, idx1 = monthly[k + 1]
        doy0 = QDate(2026, m0, d0).dayOfYear()
        doy1 = QDate(2026, m1, d1).dayOfYear()
        if doy1 <= doy0:
            doy1 += 365
        md0 = meridians[idx0]
        md1 = meridians[idx1]
        for j in range(len(hours) - 1):
            h0, h1 = hours[j], hours[j + 1]
            p00 = _point_at_hour(md0["pts"], md0["marcados"], h0)
            p10 = _point_at_hour(md1["pts"], md1["marcados"], h0)
            p11 = _point_at_hour(md1["pts"], md1["marcados"], h1)
            p01 = _point_at_hour(md0["pts"], md0["marcados"], h1)
            if None in (p00, p10, p11, p01):
                continue
            cells.append({
                "corners": [p00, p10, p11, p01],
                "idx0": idx0, "idx1": idx1,
                "m0": m0, "d0": d0, "doy0": doy0,
                "m1": m1, "d1": d1, "doy1": doy1,
                "h0": h0, "h1": h1,
            })
    return cells


def _build_dome_cache(radius: float, lat_deg: float,
                      current_month: int = 3, current_day: int = 21):
    global _DOME_CACHE
    c = _get_dome_center()
    key = (round(radius, 6), round(lat_deg, 6),
           round(_NORTH_ROTATION_DEG, 6),
           round(c.x(), 4), round(c.y(), 4), round(c.z(), 4),
           _DOME_SHOW_ANALEMAS, int(current_month), int(current_day))
    if _DOME_CACHE is not None and _DOME_CACHE.get("key") == key:
        return _DOME_CACHE

    warm = {1, 2, 3, 4, 5, 6}
    dates = [(m, 15, False) for m in range(1, 13)]
    dates.append((int(current_month), int(current_day), True))

    meridians = []
    for (m, d, special) in dates:
        pts = []
        marcados = []
        for mn in range(0, 24 * 60, _DOME_HOUR_STEP_MIN):
            h, mi = mn // 60, mn % 60
            class _S: pass
            s = _S(); s.month = m; s.day = d; s.hour = h; s.minute = mi
            try:
                az, el = _solar_position(s, lat_deg)
            except Exception:
                continue
            if el <= 0.0:
                continue
            pts.append(_dome_point(az, el, radius))
            if mi == 0 and h in _DOME_MARKED_HOURS:
                p = _dome_point(az, el, radius)
                marcados.append((*p, h))
        if len(pts) < 2:
            continue
        ends = _sunrise_sunset_points((m, d), radius, lat_deg)
        nascente, poente = ends if ends else (None, None)
        meridians.append({
            "pts": pts, "marcados": marcados,
            "nascente": nascente, "poente": poente,
            "label": f"{d}/{m}",
            "warm": (m in warm), "special": special,
            "month": m, "day": d,
        })

    analemas = _build_analemas_cache(radius, lat_deg) if _DOME_SHOW_ANALEMAS else []
    cells = _build_cells(meridians, radius, lat_deg)

    _DOME_CACHE = {
        "meridians": meridians, "analemas": analemas,
        "cells": cells,
        "radius": radius, "lat": lat_deg, "key": key,
    }
    return _DOME_CACHE


def _invalidate_dome_cache():
    global _DOME_CACHE
    _DOME_CACHE = None


# =========================================================================
# 9. Status messages / season toggle
# =========================================================================
def _show_dome_status_message(main_window) -> None:
    try:
        if main_window is not None and hasattr(main_window, "statusBar"):
            sb = main_window.statusBar()
            if sb is not None:
                global _USE_SECOND_HALF_YEAR
                periodo = _t("July to December (2nd Semester)") if _USE_SECOND_HALF_YEAR else _t("January to June (1st Semester)")
                msg = _t("Sun Dome active | Press TAB to toggle selection period (Current: {period})").format(period=periodo)
                sb.showMessage(msg, 7000)
    except Exception:
        traceback.print_exc()


def _toggle_season_groups(main_window):
    if not _SUN_DOME_ACTIVE:
        return
    focus_w = QApplication.focusWidget()
    if isinstance(focus_w, (QLineEdit, QDoubleSpinBox, QSlider, QComboBox)):
        return
    global _USE_SECOND_HALF_YEAR, _HOVER_CELL_IDX
    _USE_SECOND_HALF_YEAR = not _USE_SECOND_HALF_YEAR
    _HOVER_CELL_IDX = -1
    _invalidate_dome_cache()
    if _OVERLAY is not None:
        _OVERLAY.update()

    mw = main_window if main_window is not None else _discover_main_window()
    _show_dome_status_message(mw)

    _log(f"Alternado semestre de seleção de células (Segundo Semestre): {_USE_SECOND_HALF_YEAR}")


# =========================================================================
# 10. Clipping helper (Liang-Barsky)
# =========================================================================
def _clip_segment_to_rect(p0: QPointF, p1: QPointF, rect: QRectF):
    x0, y0, x1, y1 = p0.x(), p0.y(), p1.x(), p1.y()
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pi, qi in zip((-dx, dx, -dy, dy),
                      (x0 - rect.left(), rect.right() - x0,
                       y0 - rect.top(), rect.bottom() - y0)):
        if pi == 0.0:
            if qi < 0.0:
                return None
        else:
            t = qi / pi
            if pi < 0.0:
                if t > t1: return None
                if t > t0: t0 = t
            else:
                if t < t0: return None
                if t < t1: t1 = t
    return QPointF(x0 + t1 * dx, y0 + t1 * dy)


# =========================================================================
# 11. Location picker / scene state persistence
# =========================================================================
def _find_base_map_panel(main_window):
    for w in main_window.findChildren(QWidget):
        if type(w).__name__ == "BaseMapPanel":
            return w
    return None


def _apply_selected_map_source(base_panel) -> None:
    if base_panel is None:
        return
    src = getattr(base_panel, "_source", None)
    if src is None:
        return
    for i in range(src.count()):
        if src.itemData(i) == _SELECTED_MAP_SID:
            src.setCurrentIndex(i)
            try:
                base_panel._last_sid = _SELECTED_MAP_SID
            except Exception:
                pass
            return


def _open_native_georef_dialog(main_window):
    bp = _find_base_map_panel(main_window)
    if bp is None:
        return None
    _apply_selected_map_source(bp)
    btn = getattr(bp, "_find", None)
    lat_box = getattr(bp, "_lat", None)
    lon_box = getattr(bp, "_lon", None)
    if btn is None:
        return None
    vp = getattr(main_window, "viewport", None)
    sc = getattr(vp, "scene", None) if vp else None
    snap = None
    if sc is not None:
        snap = {"tile_layer": getattr(sc, "tile_layer", None),
                "terrain": getattr(sc, "terrain", None),
                "photo_mesh": getattr(sc, "photo_mesh", None)}
    try:
        btn.click()
    except Exception as e:
        _log(f"error clicking '_find': {e}")
        return None
    if lat_box is None or lon_box is None:
        return None
    try:
        lat, lon = float(lat_box.value()), float(lon_box.value())
    except Exception:
        return None
    if not _LOAD_MAP_TOO and sc is not None and snap is not None:
        try:
            sc.tile_layer = snap["tile_layer"]
            sc.terrain = snap["terrain"]
            sc.photo_mesh = snap["photo_mesh"]
        except Exception as e:
            _log(f"restore tile_layer error: {e}")
        if vp is not None:
            try: vp.update()
            except Exception: pass
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _change_location(main_window, lat: float, lon: float) -> None:
    sc = _get_scene(main_window)
    if sc is None:
        return
    gr = getattr(sc, "georef", None)
    if gr is not None:
        try: gr.lat = float(lat)
        except Exception: pass
        try: gr.lon = float(lon)
        except Exception: pass
    sh = _get_shadows(main_window)
    if sh is not None:
        if hasattr(sh, "latitude"): sh.latitude = lat
        if hasattr(sh, "longitude"): sh.longitude = lon
    try:
        mw = _discover_main_window()
        if mw is not None:
            tray = getattr(mw, "georef_tray", None)
            bm = getattr(tray, "base_map", None) if tray else None
            if bm is not None:
                ls = getattr(bm, "_lat", None)
                os_ = getattr(bm, "_lon", None)
                if ls is not None:
                    ls.blockSignals(True); ls.setValue(float(lat)); ls.blockSignals(False)
                if os_ is not None:
                    os_.blockSignals(True); os_.setValue(float(lon)); os_.blockSignals(False)
    except Exception:
        traceback.print_exc()
    _invalidate_dome_cache()
    _repaint(main_window)


def _save_state_to_scene(main_window) -> None:
    sc = _get_scene(main_window)
    if sc is None:
        return
    _scene_set_attr(sc, "igz_dome_active", bool(_SUN_DOME_ACTIVE))
    _scene_set_attr(sc, "igz_sun_vector_active", bool(_SUN_VECTOR_ACTIVE))
    _scene_set_attr(sc, "igz_overlay_visible", bool(_OVERLAY_VISIBLE))
    _scene_set_attr(sc, "igz_dome_diagram_scale", float(_DOME_DIAGRAM_SCALE))
    _scene_set_attr(sc, "igz_dome_show_analemas", bool(_DOME_SHOW_ANALEMAS))
    _scene_set_attr(sc, "igz_dome_show_hour_labels", bool(_DOME_SHOW_HOUR_LABELS))
    _scene_set_attr(sc, "igz_dome_show_date_labels", bool(_DOME_SHOW_DATE_LABELS))
    _scene_set_attr(sc, "igz_dome_show_compass", bool(_DOME_SHOW_COMPASS))
    _scene_set_attr(sc, "igz_export_transparent", bool(_EXPORT_TRANSPARENT_BG))
    global _DOME_CENTER_XYZ
    if _DOME_CENTER_XYZ is not None:
        _scene_set_attr(sc, "igz_dome_center",
                        [_DOME_CENTER_XYZ.x(), _DOME_CENTER_XYZ.y(),
                         _DOME_CENTER_XYZ.z()])
    else:
        _scene_set_attr(sc, "igz_dome_center", None)


def _load_state_from_scene(main_window) -> None:
    global _SUN_DOME_ACTIVE, _SUN_VECTOR_ACTIVE, _OVERLAY_VISIBLE
    global _DOME_DIAGRAM_SCALE, _DOME_SHOW_ANALEMAS
    global _DOME_SHOW_HOUR_LABELS, _DOME_SHOW_DATE_LABELS, _DOME_SHOW_COMPASS
    global _DOME_CENTER_XYZ, _EXPORT_TRANSPARENT_BG
    sc = _get_scene(main_window)
    if sc is None:
        return
    _SUN_DOME_ACTIVE = bool(_scene_get_attr(sc, "igz_dome_active", False))
    _SUN_VECTOR_ACTIVE = bool(_scene_get_attr(sc, "igz_sun_vector_active", False))
    _OVERLAY_VISIBLE = bool(_scene_get_attr(sc, "igz_overlay_visible", False))
    _DOME_DIAGRAM_SCALE = float(_scene_get_attr(sc, "igz_dome_diagram_scale", 1.0))
    _DOME_SHOW_ANALEMAS = bool(_scene_get_attr(sc, "igz_dome_show_analemas", True))
    _DOME_SHOW_HOUR_LABELS = bool(_scene_get_attr(sc, "igz_dome_show_hour_labels", True))
    _DOME_SHOW_DATE_LABELS = bool(_scene_get_attr(sc, "igz_dome_show_date_labels", True))
    _DOME_SHOW_COMPASS = bool(_scene_get_attr(sc, "igz_dome_show_compass", True))
    _EXPORT_TRANSPARENT_BG = bool(_scene_get_attr(sc, "igz_export_transparent", False))
    c = _scene_get_attr(sc, "igz_dome_center", None)
    if isinstance(c, (list, tuple)) and len(c) == 3:
        _DOME_CENTER_XYZ = QVector3D(float(c[0]), float(c[1]), float(c[2]))
    else:
        _DOME_CENTER_XYZ = None
    _invalidate_dome_cache()


# =========================================================================
# 12. Overlay state (globals)
# =========================================================================
_OVERLAY = None
_OVERLAY_VISIBLE = False


# =========================================================================
# 13. Cell geometry / hit-test helpers
# =========================================================================
def _project_corners(vp, cell):
    quad = []
    for (x, y, z) in cell["corners"]:
        p = vp.world_to_pixel(QVector3D(x, y, z))
        if p is None:
            return None
        quad.append(QPointF(float(p[0]), float(p[1])))
    return quad


def _point_in_quad(px: float, py: float, quad):
    inside = False
    n = len(quad)
    j = n - 1
    for i in range(n):
        xi, yi = quad[i].x(), quad[i].y()
        xj, yj = quad[j].x(), quad[j].y()
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / ((yj - yi) + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _hover_cell_index(vp, px: float, py: float, cache) -> int:
    for k, cell in enumerate(cache.get("cells", [])):
        quad = _project_corners(vp, cell)
        if quad is None:
            continue
        if _point_in_quad(px, py, quad):
            return k
    return -1


def _bary(a, b, c, px, py):
    ax, ay = a.x(), a.y()
    bx, by = b.x(), b.y()
    cx, cy = c.x(), c.y()
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(d) < 1e-12:
        return None
    u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
    v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
    return (u, v, 1.0 - u - v)


def _pick_cell_datetime(cell, px, py, quad):
    b1 = _bary(quad[0], quad[1], quad[2], px, py)
    if b1 is not None and b1[0] >= -1e-6 and b1[1] >= -1e-6 and b1[2] >= -1e-6:
        u, v = b1[0], b1[1]
    else:
        b2 = _bary(quad[0], quad[2], quad[3], px, py)
        if b2 is None:
            return None
        u, v = b2[0], b2[1]

    c00, c10, c11, c01 = quad[0], quad[1], quad[2], quad[3]

    def P_approx(u, v):
        x = ((1 - u) * (1 - v) * c00.x() + u * (1 - v) * c10.x()
             + u * v * c11.x() + (1 - u) * v * c01.x())
        y = ((1 - u) * (1 - v) * c00.y() + u * (1 - v) * c10.y()
             + u * v * c11.y() + (1 - u) * v * c01.y())
        return x, y

    def dPu(u, v):
        return ((1 - v) * (c10.x() - c00.x()) + v * (c11.x() - c01.x()),
                (1 - v) * (c10.y() - c00.y()) + v * (c11.y() - c01.y()))

    def dPv(u, v):
        return ((1 - u) * (c01.x() - c00.x()) + u * (c11.x() - c10.x()),
                (1 - u) * (c01.y() - c00.y()) + u * (c11.y() - c10.y()))

    lx10 = c10.x() - c00.x(); ly10 = c10.y() - c00.y()
    lx01 = c01.x() - c00.x(); ly01 = c01.y() - c00.y()
    u = 0.5; v = 0.5
    try:
        du = (lx10 * lx10 + ly10 * ly10)
        dv = (lx01 * lx01 + ly01 * ly01)
        if du > 1e-9:
            u = ((px - c00.x()) * lx10 + (py - c00.y()) * ly10) / du
        if dv > 1e-9:
            v = ((px - c00.x()) * lx01 + (py - c00.y()) * ly01) / dv
    except Exception:
        pass

    u = max(-0.2, min(1.2, u))
    v = max(-0.2, min(1.2, v))

    for _ in range(6):
        x, y = P_approx(u, v)
        fx, fy = x - px, y - py
        if abs(fx) < 1e-3 and abs(fy) < 1e-3:
            break
        ax, ay = dPu(u, v)
        bx, by = dPv(u, v)
        det = ax * by - ay * bx
        if abs(det) < 1e-12:
            break
        du_ = (-fx * by + fy * bx) / det
        dv_ = (-fy * ax + fx * ay) / det
        u += du_
        v += dv_

    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))

    h = cell["h0"] + v * (cell["h1"] - cell["h0"])
    doy = cell["doy0"] + u * (cell["doy1"] - cell["doy0"])
    doy = int(round(doy)) % 365
    if doy == 0:
        doy = 365
    d = QDate(2026, 1, 1).addDays(doy - 1)
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm >= 60:
        hh += 1
        mm -= 60
    return (d.month(), d.day(), hh % 24, mm)


# =========================================================================
# 14. Snap helpers / uses_snap patch
# =========================================================================
def _call_vp_snap(vp, x, y, mods=None):
    fn = getattr(vp, "_snap_at", None)
    if not callable(fn):
        return None
    if mods is None:
        try:
            mods = QApplication.keyboardModifiers()
        except Exception:
            mods = Qt.NoModifier
    try:
        res = fn(float(x), float(y), mods)
    except TypeError:
        res = None
        for m in (mods, Qt.NoModifier, 0, None):
            try:
                res = fn(float(x), float(y), m)
                break
            except Exception:
                continue
    except Exception:
        traceback.print_exc()
        return None
    if res is None:
        return None

    kind = getattr(res, "kind", None)
    if kind is None or kind == "none" or kind == "":
        return None

    pt = getattr(res, "point", None)
    if pt is not None:
        return pt
    if isinstance(res, (tuple, list)) and res:
        return res[0]
    if isinstance(res, QVector3D):
        return res
    return None


def _snap_to_scene_vertex(vp, scene, x, y, tol_px=10.0):
    if vp is None or scene is None:
        return None
    best = None

    def _consider(pos):
        nonlocal best
        if pos is None:
            return
        try:
            p = vp.world_to_pixel(QVector3D(pos.x(), pos.y(), pos.z()))
        except Exception:
            return
        if p is None:
            return
        d = math.hypot(float(p[0]) - x, float(p[1]) - y)
        if d <= tol_px and (best is None or d < best[0]):
            best = (d, QVector3D(pos.x(), pos.y(), pos.z()))

    def _iter_positions():
        mesh = getattr(scene, "mesh", None)
        if mesh is not None:
            for v in getattr(mesh, "vertices", []) or []:
                for attr in ("position", "co", "p", "xyz"):
                    if hasattr(v, attr):
                        yield getattr(v, attr); break
        try:
            for f in getattr(scene, "faces", []) or []:
                for attr in ("vertices", "loop"):
                    vs = getattr(f, attr, None)
                    if vs is None:
                        continue
                    for v in vs:
                        if hasattr(v, "position"):
                            yield v.position
                        elif hasattr(v, "co"):
                            yield v.co
                    break
        except Exception:
            pass

    try:
        for pos in _iter_positions():
            _consider(pos)
    except Exception:
        traceback.print_exc()

    if best is not None:
        return best[1]
    return None


def _pick_with_osnap(vp, x, y, tol_px=12.0):
    if vp is None:
        return None, "no_vp"

    try:
        ls = getattr(vp, "last_snap", None)
        if ls is not None:
            k = getattr(ls, "kind", "none") or "none"
            p = getattr(ls, "point", None)
            if p is not None and k not in ("none", ""):
                return p, k
    except Exception:
        traceback.print_exc()

    try:
        fn = getattr(vp, "pick_vertex", None)
        if callable(fn):
            res = fn(float(x), float(y))
            if res is not None:
                p = getattr(res, "point", None)
                if p is None:
                    p = getattr(res, "position", None) or getattr(res, "co", None)
                if p is not None:
                    if not isinstance(p, QVector3D):
                        p = QVector3D(p)
                    return p, "vertex"
                if isinstance(res, QVector3D):
                    return res, "vertex"
    except Exception:
        traceback.print_exc()

    try:
        fn = getattr(vp, "pick_edge", None) or getattr(vp, "pick_visible_edge", None)
        if callable(fn):
            res = fn(float(x), float(y))
            if res is not None:
                p = (getattr(res, "point", None)
                     or getattr(res, "closest_point", None))
                if p is not None:
                    if not isinstance(p, QVector3D):
                        p = QVector3D(p)
                    return p, "edge"
                if isinstance(res, QVector3D):
                    return res, "edge"
    except Exception:
        traceback.print_exc()

    try:
        fn = getattr(vp, "edge_point_under_cursor", None)
        if callable(fn):
            res = fn(float(x), float(y))
            if isinstance(res, QVector3D):
                return res, "edge_point"
            if res is not None:
                p = getattr(res, "point", None)
                if p is not None:
                    if not isinstance(p, QVector3D):
                        p = QVector3D(p)
                    return p, "edge_point"
    except Exception:
        traceback.print_exc()

    try:
        fn = getattr(vp, "pick_face", None) or getattr(vp, "pick_face_any", None)
        if callable(fn):
            res = fn(float(x), float(y))
            if res is not None:
                p = (getattr(res, "point", None)
                     or getattr(res, "hit_point", None))
                if p is not None:
                    if not isinstance(p, QVector3D):
                        p = QVector3D(p)
                    return p, "face"
                if isinstance(res, QVector3D):
                    return res, "face"
    except Exception:
        traceback.print_exc()

    p = _call_vp_snap(vp, x, y)
    if p is not None:
        return p, "snap_at"

    try:
        mw = _discover_main_window()
        sc = _get_scene(mw) if mw is not None else None
        p = _snap_to_scene_vertex(vp, sc, x, y, tol_px)
        if p is not None:
            return p, "vertex_fallback"
    except Exception:
        traceback.print_exc()

    try:
        fn = getattr(vp, "_world_under_cursor", None) or \
             getattr(vp, "_world_from_pixel", None)
        if callable(fn):
            res = fn(int(x), int(y))
            if isinstance(res, QVector3D):
                return res, "plane"
            if res is not None:
                p = getattr(res, "point", None)
                if p is not None:
                    if not isinstance(p, QVector3D):
                        p = QVector3D(p)
                    return p, "plane"
    except Exception:
        traceback.print_exc()

    return None, "miss"


_ORIG_USES_SNAP_FOR_PICKING = None
_USES_SNAP_PATCHED = False


def _patch_uses_snap_for_picking(vp):
    global _ORIG_USES_SNAP_FOR_PICKING, _USES_SNAP_PATCHED
    if vp is None:
        return
    if _USES_SNAP_PATCHED:
        return
    tool = getattr(vp, "active_tool", None)
    if tool is None:
        _log("Set Center: active_tool ausente; snap pode não funcionar")
        return
    try:
        _ORIG_USES_SNAP_FOR_PICKING = getattr(tool, "uses_snap", False)
    except Exception:
        _ORIG_USES_SNAP_FOR_PICKING = False
    try:
        setattr(tool, "uses_snap", True)
        _USES_SNAP_PATCHED = True
        _log(f"Set Center: uses_snap=True em {type(tool).__name__} "
             f"(era {_ORIG_USES_SNAP_FOR_PICKING})")
    except Exception:
        traceback.print_exc()


def _restore_uses_snap_after_picking(vp):
    global _ORIG_USES_SNAP_FOR_PICKING, _USES_SNAP_PATCHED
    if vp is None:
        return
    if not _USES_SNAP_PATCHED:
        return
    tool = getattr(vp, "active_tool", None)
    if tool is not None and _ORIG_USES_SNAP_FOR_PICKING is not None:
        try:
            setattr(tool, "uses_snap", bool(_ORIG_USES_SNAP_FOR_PICKING))
        except Exception:
            traceback.print_exc()
    _ORIG_USES_SNAP_FOR_PICKING = None
    _USES_SNAP_PATCHED = False


# =========================================================================
# 15. Cursor helpers
# =========================================================================
_PICK_FILTER_TARGETS = []
_CENTER_CURSOR_APPLIED = False


def _set_dome_hover_cursor(main_window, on: bool):
    global _HOVER_CURSOR_APPLIED
    if _HOVER_CURSOR_APPLIED == on:
        return
    vp = _get_viewport(main_window)
    try:
        if on:
            cur = _load_custom_cursor("sunpath_cursor", main_window)
            if vp is not None:
                vp.setCursor(cur)
            if _OVERLAY is not None and not _OVERLAY.testAttribute(
                    Qt.WA_TransparentForMouseEvents):
                _OVERLAY.setCursor(cur)
        else:
            if vp is not None:
                vp.unsetCursor()
            if _OVERLAY is not None and not _OVERLAY.testAttribute(
                    Qt.WA_TransparentForMouseEvents):
                _OVERLAY.unsetCursor()
    except Exception:
        traceback.print_exc()
    _HOVER_CURSOR_APPLIED = on


def _set_center_cursor(main_window, on: bool):
    global _CENTER_CURSOR_APPLIED
    if _CENTER_CURSOR_APPLIED == on:
        return
    vp = _get_viewport(main_window)
    try:
        if on:
            cur = _load_custom_cursor("sunpath_center", main_window)
            if vp is not None:
                vp.setCursor(cur)
            if _OVERLAY is not None:
                _OVERLAY.setCursor(cur)
        else:
            if vp is not None:
                vp.unsetCursor()
            if _OVERLAY is not None:
                _OVERLAY.unsetCursor()
    except Exception:
        traceback.print_exc()
    _CENTER_CURSOR_APPLIED = on


# =========================================================================
# 16. Viewport pick event filter
# =========================================================================
class _ViewportPickEventFilter(QObject):
    def __init__(self, main_window, dialog_to_restore=None):
        super().__init__()
        self._mw = main_window
        self._dlg = dialog_to_restore

    def _cache_for_current(self):
        lat, _ = _get_georef(self._mw)
        sh = _get_shadows(self._mw)
        cm = int(sh.month) if sh is not None else 3
        cd = int(sh.day) if sh is not None else 21
        return _build_dome_cache(_dome_radius(), lat, cm, cd)

    def eventFilter(self, obj, ev):
        global _PICKING_CENTER, _PICK_FILTER_TARGETS
        global _DOME_CENTER_XYZ, _HOVER_CELL_IDX
        global _OVERLAY_VISIBLE, _SUN_VECTOR_ACTIVE
        try:
            if (_PICKING_CENTER
                    and ((ev.type() == QEvent.KeyPress
                          and ev.key() == Qt.Key_Escape)
                         or (ev.type() == QEvent.MouseButtonPress
                             and ev.button() == Qt.RightButton))):
                _PICKING_CENTER = False
                for tgt in list(_PICK_FILTER_TARGETS):
                    try:
                        tgt.removeEventFilter(self)
                    except Exception:
                        pass
                _PICK_FILTER_TARGETS = []
                _restore_uses_snap_after_picking(_get_viewport(self._mw))
                _set_center_cursor(self._mw, False)
                if _OVERLAY is not None:
                    try:
                        _OVERLAY._picking_preview = None
                        _OVERLAY.update()
                    except Exception:
                        pass
                ev.accept()
                return True

            if _PICKING_CENTER:
                if ev.type() == QEvent.MouseMove:
                    vp = _get_viewport(self._mw)
                    if vp is not None and _OVERLAY is not None:
                        try:
                            x = float(ev.position().x())
                            y = float(ev.position().y())
                            pt, kind = _pick_with_osnap(vp, x, y, 12.0)
                            _OVERLAY._picking_preview = pt
                            _OVERLAY._picking_preview_kind = kind
                            _OVERLAY.update()
                        except Exception:
                            traceback.print_exc()
                    return False

                if (ev.type() == QEvent.MouseButtonPress
                        and ev.button() == Qt.LeftButton):
                    pos = ev.position()
                    vp = _get_viewport(self._mw)
                    pt_3d = None
                    snap_kind = None
                    if vp is not None:
                        x, y = float(pos.x()), float(pos.y())
                        pt_3d, snap_kind = _pick_with_osnap(vp, x, y, 12.0)

                    _log(f"Set Center pick: kind={snap_kind} pt={pt_3d}")

                    if pt_3d is None:
                        pt_3d = QVector3D(0, 0, 0)
                        snap_kind = "origin"

                    if isinstance(pt_3d, QVector3D):
                        _DOME_CENTER_XYZ = pt_3d
                    elif isinstance(pt_3d, (tuple, list)) and len(pt_3d) >= 2:
                        z = float(pt_3d[2]) if len(pt_3d) > 2 else 0.0
                        _DOME_CENTER_XYZ = QVector3D(
                            float(pt_3d[0]), float(pt_3d[1]), z)

                    _PICKING_CENTER = False
                    for tgt in list(_PICK_FILTER_TARGETS):
                        try:
                            tgt.removeEventFilter(self)
                        except Exception:
                            pass
                    _PICK_FILTER_TARGETS = []
                    _restore_uses_snap_after_picking(vp)
                    _set_center_cursor(self._mw, False)

                    if _OVERLAY is not None:
                        try:
                            _OVERLAY._picking_preview = None
                            _OVERLAY._picking_preview_kind = "none"
                            _OVERLAY.update()
                        except Exception:
                            pass

                    _invalidate_dome_cache()
                    _save_state_to_scene(self._mw)
                    _repaint(self._mw)

                    if _DIALOG is not None and hasattr(_DIALOG, "_lbl_center_val"):
                        c = _get_dome_center()
                        try:
                            _DIALOG._lbl_center_val.setText(
                                f"{c.x():.2f}, {c.y():.2f}, {c.z():.2f}")
                        except Exception:
                            pass

                    if self._dlg is not None:
                        try:
                            self._dlg.show()
                            self._dlg.raise_()
                            self._dlg.activateWindow()
                        except Exception:
                            pass
                    ev.accept()
                    return True
                return False

            if not _SUN_DOME_ACTIVE:
                return False

            if ev.type() == QEvent.MouseMove:
                pos = ev.position()
                vp = _get_viewport(self._mw)
                if vp is None:
                    return False
                cache = self._cache_for_current()
                idx = _hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx != _HOVER_CELL_IDX:
                    _HOVER_CELL_IDX = idx
                    _set_dome_hover_cursor(self._mw, idx >= 0)
                    if _OVERLAY is not None:
                        _OVERLAY.update()
                return False

            if (ev.type() == QEvent.MouseButtonPress
                    and ev.button() == Qt.LeftButton):
                pos = ev.position()
                vp = _get_viewport(self._mw)
                if vp is None:
                    return False
                cache = self._cache_for_current()
                idx = _hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx < 0:
                    return False
                cell = cache["cells"][idx]
                quad = _project_corners(vp, cell)
                if quad is None:
                    return False
                res = _pick_cell_datetime(cell, pos.x(), pos.y(), quad)
                if res is None:
                    return False
                m, d, h, mi = res
                sh = _get_shadows(self._mw)
                if sh is not None:
                    _shadows_set_date(sh, m, d)
                    _shadows_set_time(sh, h, mi)
                _log(f"dome cell pick: {d:02d}/{m:02d} {h:02d}:{mi:02d}")

                if _OVERLAY_VISIBLE:
                    _OVERLAY_VISIBLE = False
                    for a, en, _ in _LABELED_ACTIONS:
                        if en == "Sun Arrow":
                            a.blockSignals(True)
                            a.setChecked(False)
                            a.blockSignals(False)
                    if _DIALOG is not None and hasattr(_DIALOG, "_btn_toggle_arrow"):
                        _DIALOG._btn_toggle_arrow.blockSignals(True)
                        _DIALOG._btn_toggle_arrow.setChecked(False)
                        _DIALOG._btn_toggle_arrow.blockSignals(False)

                if not _SUN_VECTOR_ACTIVE:
                    _SUN_VECTOR_ACTIVE = True
                    for a, en, _ in _LABELED_ACTIONS:
                        if en == "Sun Vector":
                            a.blockSignals(True)
                            a.setChecked(True)
                            a.blockSignals(False)
                    if _DIALOG is not None and hasattr(_DIALOG, "_btn_toggle_vector"):
                        _DIALOG._btn_toggle_vector.blockSignals(True)
                        _DIALOG._btn_toggle_vector.setChecked(True)
                        _DIALOG._btn_toggle_vector.blockSignals(False)

                _sync_overlay_visibility(self._mw)

                _invalidate_dome_cache()
                _save_state_to_scene(self._mw)
                _repaint(self._mw)
                if _DIALOG is not None:
                    try:
                        doy = QDate(2026, m, d).dayOfYear()
                        mins = h * 60 + mi
                        if hasattr(_DIALOG, "_sld_date"):
                            _DIALOG._sld_date.blockSignals(True)
                            _DIALOG._sld_date.setValue(doy)
                            _DIALOG._sld_date.blockSignals(False)
                        if hasattr(_DIALOG, "_sld_time"):
                            _DIALOG._sld_time.blockSignals(True)
                            _DIALOG._sld_time.setValue(mins)
                            _DIALOG._sld_time.blockSignals(False)
                        if hasattr(_DIALOG, "_refresh_solar_readout"):
                            _DIALOG._refresh_solar_readout()
                    except Exception:
                        traceback.print_exc()
                ev.accept()
                return True
            return False
        except Exception:
            _log("EF: EXCEPTION")
            traceback.print_exc()
            return False


_PICK_FILTER = None


# =========================================================================
# 17. Start picking center
# =========================================================================
def _start_picking_center(main_window, dialog_to_restore=None):
    global _PICKING_CENTER, _PICK_FILTER, _PICK_FILTER_TARGETS
    vp = _get_viewport(main_window)
    if vp is None:
        _log("Set Center: viewport not found")
        return
    _PICKING_CENTER = True
    _patch_uses_snap_for_picking(vp)
    _ensure_overlay(main_window)

    if _PICK_FILTER is None:
        _PICK_FILTER = _ViewportPickEventFilter(main_window, dialog_to_restore)
    else:
        _PICK_FILTER._dlg = dialog_to_restore or _PICK_FILTER._dlg
        _PICK_FILTER._mw = main_window

    if vp not in _PICK_FILTER_TARGETS:
        try:
            vp.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(vp)
        except Exception:
            traceback.print_exc()

    ov = _OVERLAY
    if ov is not None:
        try:
            ov._picking_preview = None
            ov._picking_preview_kind = "none"
            ov.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            traceback.print_exc()

    _set_center_cursor(main_window, True)
    _log(f"Set Center activated (targets={len(_PICK_FILTER_TARGETS)})")


# =========================================================================
# 18. Sun-arrow overlay (widget)
# =========================================================================
class _SunArrowOverlay(QWidget):
    def __init__(self, viewport, main_window):
        super().__init__(viewport)
        self._vp = viewport
        self._mw = main_window
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._hover_labels = []
        viewport.installEventFilter(self)
        self._resize_to_parent()
        self._radius = 44
        self._margin_right = 90
        self._margin_top = 24
        self._custom_center = None
        self.show()
        self.raise_()
        self._info_box_width = 186
        self._info_box_height = 96
        self._slider_left_pad = 40
        self._slider_right_pad = 12
        self._slider_h = 6
        self._slider_handle_r = 5
        self._slider_gap = 20
        self._drag_slider = None
        self._picking_preview = None
        self._picking_preview_kind = "none"

        f = self.font()
        f.setPointSize(8)
        f.setBold(False)
        self._font_label_cache = f

    def _resize_to_parent(self):
        if self._vp is not None:
            self.setGeometry(0, 0, self._vp.width(), self._vp.height())

    def eventFilter(self, obj, ev):
        try:
            if obj is self._vp and ev.type() == QEvent.Resize:
                self._resize_to_parent()
        except Exception:
            pass
        return False

    def _get_center(self) -> QPointF:
        if self._custom_center is not None:
            return self._custom_center
        cx = self.width() - self._margin_right - self._radius
        cy = self._margin_top + self._radius
        return QPointF(max(self._radius, cx), max(self._radius, cy))

    def _info_box_rect(self) -> QRectF:
        c = self._get_center()
        w, h = self._info_box_width, self._info_box_height
        return QRectF(c.x() - w / 2, c.y() + self._radius + 8, w, h)

    def _slider_rects(self):
        box = self._info_box_rect()
        top = box.y() + 4 + 3 * 16 + 6
        left = box.x() + self._slider_left_pad
        w = box.width() - self._slider_left_pad - self._slider_right_pad
        return (QRectF(left, top, w, self._slider_handle_r * 2),
                QRectF(left, top + self._slider_gap, w,
                       self._slider_handle_r * 2))

    def _hit_slider(self, pos: QPointF):
        rd, rt = self._slider_rects()
        p = 6
        if rd.adjusted(0, -p, 0, p).contains(pos): return "date"
        if rt.adjusted(0, -p, 0, p).contains(pos): return "time"
        return None

    def _apply_slider_from_x(self, which, screen_x):
        if self._mw is None:
            return
        rd, rt = self._slider_rects()
        rect = rd if which == "date" else rt
        if rect.width() <= 0:
            return
        t = max(0.0, min(1.0, (screen_x - rect.x()) / rect.width()))
        sh = _get_shadows(self._mw)
        if sh is None:
            return
        if which == "date":
            doy = 1 + int(round(t * 364.0))
            m, d = _day_of_year_to_date(doy)
            _shadows_set_date(sh, m, d)
            _invalidate_dome_cache()
        else:
            mins = int(round(t * 1439.0))
            _shadows_set_time(sh, mins // 60, mins % 60)
        if _DIALOG is not None:
            try:
                if which == "date" and hasattr(_DIALOG, "_sld_date"):
                    _DIALOG._sld_date.blockSignals(True)
                    _DIALOG._sld_date.setValue(doy)
                    _DIALOG._sld_date.blockSignals(False)
                    if hasattr(_DIALOG, "_lbl_date"):
                        _DIALOG._lbl_date.setText(_DIALOG._date_text(doy))
                elif which == "time" and hasattr(_DIALOG, "_sld_time"):
                    _DIALOG._sld_time.blockSignals(True)
                    _DIALOG._sld_time.setValue(mins)
                    _DIALOG._sld_time.blockSignals(False)
                    if hasattr(_DIALOG, "_lbl_time"):
                        _DIALOG._lbl_time.setText(_DIALOG._time_text(mins))
                if hasattr(_DIALOG, "_refresh_solar_readout"):
                    _DIALOG._refresh_solar_readout()
            except Exception:
                traceback.print_exc()
        _repaint(self._mw)

    def mousePressEvent(self, event):
        if _PICKING_CENTER:
            event.ignore(); return
        if not _OVERLAY_VISIBLE:
            super().mousePressEvent(event); return
        if event.button() == Qt.LeftButton:
            pos = event.position()
            hit = self._hit_slider(pos)
            if hit is not None:
                self._drag_slider = hit
                self._apply_slider_from_x(hit, pos.x())
                event.accept(); return
            c = self._get_center()
            box = self._info_box_rect()
            rect = QRectF(c.x() - self._info_box_width / 2,
                          c.y() - self._radius,
                          self._info_box_width,
                          self._radius * 2 + box.height() + 8)
            if rect.contains(pos):
                self._dragging = True
                self._drag_offset = c - pos
                event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if _PICKING_CENTER:
            event.ignore(); return

        pos = event.position()
        c = self._get_center()
        box = self._info_box_rect()
        info_rect = QRectF(c.x() - self._info_box_width / 2,
                           c.y() - self._radius,
                           self._info_box_width,
                           self._radius * 2 + box.height() + 8)

        if not info_rect.contains(pos) and _SUN_DOME_ACTIVE:
            global _HOVER_CELL_IDX
            vp = self._vp
            if vp is not None:
                lat, _ = _get_georef(self._mw)
                sh = _get_shadows(self._mw)
                cm = int(sh.month) if sh is not None else 3
                cd = int(sh.day) if sh is not None else 21
                cache = _build_dome_cache(_dome_radius(), lat, cm, cd)
                idx = _hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx != _HOVER_CELL_IDX:
                    _HOVER_CELL_IDX = idx
                    _set_dome_hover_cursor(self._mw, idx >= 0)
                    self.update()

        if self._drag_slider is not None:
            self._apply_slider_from_x(self._drag_slider, pos.x())
            event.accept(); return
        if getattr(self, "_dragging", False):
            self._custom_center = pos + self._drag_offset
            self.update()
            event.accept(); return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if _PICKING_CENTER:
            event.ignore(); return
        if self._drag_slider is not None:
            self._drag_slider = None; event.accept(); return
        if getattr(self, "_dragging", False):
            self._dragging = False; event.accept(); return
        super().mouseReleaseEvent(event)

    def _draw_analemas(self, painter: QPainter, cache):
        if self._vp is None:
            return
        pen = QPen(QColor(140, 140, 140, 200), 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for an in cache.get("analemas", []):
            prev = None
            for (x, y, z) in an["pts"]:
                p = self._vp.world_to_pixel(QVector3D(x, y, z))
                if p is not None:
                    cur = QPointF(float(p[0]), float(p[1]))
                    if prev is not None:
                        painter.drawLine(prev, cur)
                    prev = cur
                else:
                    prev = None

    def _draw_hover_cell(self, painter: QPainter, cache):
        if _HOVER_CELL_IDX < 0:
            return
        cells = cache.get("cells", [])
        if _HOVER_CELL_IDX >= len(cells):
            return
        cell = cells[_HOVER_CELL_IDX]
        quad = _project_corners(self._vp, cell)
        if quad is None:
            return
        poly = QPolygonF(quad)
        painter.setPen(QPen(QColor(255, 215, 0, 240), 2.2))
        painter.setBrush(QBrush(QColor(255, 215, 0, 70)))
        painter.drawPolygon(poly)

    def _draw_hover_cell_labels(self, painter: QPainter, cache):
        if _HOVER_CELL_IDX < 0:
            return
        cells = cache.get("cells", [])
        if _HOVER_CELL_IDX >= len(cells):
            return
        cell = cells[_HOVER_CELL_IDX]
        quad = _project_corners(self._vp, cell)
        if quad is None or len(quad) < 4:
            return

        corners_meta = [
            (cell["m0"], cell["d0"], cell["h0"]),
            (cell["m1"], cell["d1"], cell["h0"]),
            (cell["m1"], cell["d1"], cell["h1"]),
            (cell["m0"], cell["d0"], cell["h1"]),
        ]

        from PySide6.QtGui import QFont, QFontMetrics

        font = QFont("Arial", 8)
        font.setBold(True)
        fm = QFontMetrics(font)

        painter.save()
        for (pt_screen, (m, d, h)) in zip(quad, corners_meta):
            text = f"{d}/{m}: {h}h-0"
            w = fm.horizontalAdvance(text) + 6
            h_box = fm.height() + 2
            px = int(pt_screen.x())
            py = int(pt_screen.y())
            box_rect = QRectF(px - w / 2, py - h_box - 6, w, h_box)
            painter.setPen(QPen(QColor(180, 140, 60), 1))
            painter.setBrush(QBrush(QColor(255, 255, 220, 240)))
            painter.drawRoundedRect(box_rect, 3, 3)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setFont(font)
            painter.drawText(box_rect, Qt.AlignCenter, text)
        painter.restore()

    def _draw_compass_xy(self, painter: QPainter, radius: float):
        if self._vp is None or not _DOME_SHOW_COMPASS:
            return
        pen_ring = QPen(QColor(140, 220, 140, 200), 1.4)
        pen_tick = QPen(QColor(140, 220, 140, 160), 1)
        c = _get_dome_center()
        for r in (radius, radius * 0.9):
            painter.setPen(pen_ring)
            painter.setBrush(Qt.NoBrush)
            prev = None
            for az in range(0, 361, 5):
                ar = math.radians(az)
                x, y = r * math.sin(ar), r * math.cos(ar)
                xr, yr, zr = _rotate_north(x, y, 0.0)
                p = self._vp.world_to_pixel(
                    QVector3D(xr + c.x(), yr + c.y(), zr + c.z()))
                if p is not None:
                    cur = QPointF(float(p[0]), float(p[1]))
                    if prev is not None:
                        painter.drawLine(prev, cur)
                    prev = cur
                else:
                    prev = None
        painter.setPen(pen_tick)
        for az in range(0, 360, _DOME_COMPASS_STEP_DEG):
            ar = math.radians(az)
            xi, yi = radius * 0.9 * math.sin(ar), radius * 0.9 * math.cos(ar)
            xo, yo = radius * 1.0 * math.sin(ar), radius * 1.0 * math.cos(ar)
            xir, yir, _ = _rotate_north(xi, yi, 0.0)
            xor, yor, _ = _rotate_north(xo, yo, 0.0)
            p1 = self._vp.world_to_pixel(
                QVector3D(xir + c.x(), yir + c.y(), c.z()))
            p2 = self._vp.world_to_pixel(
                QVector3D(xor + c.x(), yor + c.y(), c.z()))
            if p1 is not None and p2 is not None:
                painter.drawLine(QPointF(float(p1[0]), float(p1[1])),
                                 QPointF(float(p2[0]), float(p2[1])))
        a = math.radians(_NORTH_ROTATION_DEG)
        nx, ny = math.sin(a), math.cos(a)
        pc = self._vp.world_to_pixel(c)
        pt = self._vp.world_to_pixel(
            QVector3D(nx * radius * 1.1 + c.x(),
                      ny * radius * 1.1 + c.y(), c.z()))
        if pc is not None and pt is not None:
            P = QPointF(float(pc[0]), float(pc[1]))
            T = QPointF(float(pt[0]), float(pt[1]))
            painter.setPen(QPen(QColor(180, 150, 220, 230), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(P, T)
            dx, dy = T.x() - P.x(), T.y() - P.y()
            L = math.hypot(dx, dy)
            if L > 1e-6:
                ux, uy = dx / L, dy / L
                nx_, ny_ = -uy, ux
                s = 10
                bx, by = T.x() - ux * s, T.y() - uy * s
                tri = [T,
                       QPointF(bx + nx_ * s * 0.5, by + ny_ * s * 0.5),
                       QPointF(bx - nx_ * s * 0.5, by - ny_ * s * 0.5)]
                painter.setBrush(QBrush(QColor(180, 150, 220, 230)))
                painter.drawPolygon(tri)
            painter.setPen(QPen(QColor(180, 150, 220, 230), 1))
            f = painter.font(); f.setPointSize(10); f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(T.x() - 10, T.y() - 22, 20, 18),
                             Qt.AlignCenter, "N")

    def _draw_dome(self, painter: QPainter, cache):
        if self._vp is None:
            return
        pen_warm = QPen(QColor(40, 90, 220, 200), 1.4, Qt.SolidLine)
        pen_cold = QPen(QColor(40, 90, 220, 200), 1.4, Qt.DashLine)
        pen_special = QPen(QColor(180, 150, 220, 230), 1.8, Qt.SolidLine)
        pen_pt = QPen(QColor(40, 90, 220, 255), 1)
        brush_pt = QBrush(QColor(40, 90, 220, 255))
        pen_pt_special = QPen(QColor(220, 40, 40, 255), 1)
        brush_pt_special = QBrush(QColor(220, 40, 40, 255))
        f_label = painter.font(); f_label.setPointSize(7); f_label.setBold(False)
        f_hour = painter.font(); f_hour.setPointSize(7); f_hour.setBold(False)

        for md in cache["meridians"]:
            is_special = md.get("special", False)
            if is_special:
                pen_mer = pen_special
            elif md["warm"]:
                pen_mer = pen_warm
            else:
                pen_mer = pen_cold
            pen_pt_local = pen_pt_special if is_special else pen_pt
            brush_pt_local = brush_pt_special if is_special else brush_pt

            painter.setPen(pen_mer)
            painter.setBrush(Qt.NoBrush)
            prev = None
            for (x, y, z) in md["pts"]:
                p = self._vp.world_to_pixel(QVector3D(x, y, z))
                if p is not None:
                    cur = QPointF(float(p[0]), float(p[1]))
                    if prev is not None:
                        painter.drawLine(prev, cur)
                    prev = cur
                else:
                    prev = None
            painter.setPen(pen_pt_local)
            painter.setBrush(brush_pt_local)
            for (x, y, z, h) in md["marcados"]:
                p = self._vp.world_to_pixel(QVector3D(x, y, z))
                if p is None:
                    continue
                px, py = float(p[0]), float(p[1])
                painter.drawEllipse(QPointF(px, py), 1.5, 1.5)
                if is_special and _DOME_SHOW_HOUR_LABELS:
                    painter.setFont(f_hour)
                    painter.setPen(QPen(QColor(60, 60, 60, 240), 1))
                    painter.drawText(QRectF(px + 5, py - 7, 30, 14),
                                     Qt.AlignLeft | Qt.AlignVCenter, str(h))
                    painter.setPen(pen_pt_local)
                    painter.setBrush(brush_pt_local)
            if _DOME_SHOW_DATE_LABELS:
                painter.setFont(f_label)
                painter.setPen(QPen(QColor(0, 0, 0, 255), 1))
                for key in ("nascente", "poente"):
                    p3 = md.get(key)
                    if p3 is None:
                        continue
                    p = self._vp.world_to_pixel(QVector3D(*p3))
                    if p is not None:
                        painter.drawText(
                            QRectF(float(p[0]) - 20, float(p[1]) - 7, 40, 14),
                            Qt.AlignCenter, md["label"])

    def paintEvent(self, _ev):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            if (self._vp is not None
                    and (self.width() != self._vp.width()
                         or self.height() != self._vp.height())):
                self._resize_to_parent()

            if _SUN_DOME_ACTIVE and self._vp is not None:
                try:
                    lat, _ = _get_georef(self._mw)
                    sh_d = _get_shadows(self._mw)
                    cm, cd = 3, 21
                    if sh_d is not None:
                        try:
                            cm, cd = int(sh_d.month), int(sh_d.day)
                        except Exception:
                            pass
                    cache = _build_dome_cache(_dome_radius(), lat, cm, cd)
                    self._draw_compass_xy(painter, _dome_radius())
                    self._draw_analemas(painter, cache)
                    self._draw_dome(painter, cache)
                    self._draw_hover_cell(painter, cache)
                    self._draw_hover_cell_labels(painter, cache)

                    painter.save()
                    f_mode = painter.font()
                    f_mode.setPointSize(8)
                    f_mode.setBold(True)
                    painter.setFont(f_mode)
                    painter.setPen(QPen(QColor(40, 90, 220, 230), 1))
                    periodo_txt = _t("Period: Jul-Dec (TAB)") if _USE_SECOND_HALF_YEAR else _t("Period: Jan-Jun (TAB)")
                    painter.drawText(QRectF(15, self.height() - 30, 200, 20), Qt.AlignLeft, periodo_txt)
                    painter.restore()
                except Exception:
                    traceback.print_exc()

            if _PICKING_CENTER and self._vp is not None \
                    and self._picking_preview is not None:
                try:
                    p = self._vp.world_to_pixel(self._picking_preview)
                    if p is not None:
                        px, py = float(p[0]), float(p[1])
                        k = getattr(self, "_picking_preview_kind", "none")
                        if k in ("vertex", "vertex_fallback"):
                            col = QColor(255, 215, 0, 240)
                        elif k in ("edge", "edge_point"):
                            col = QColor(80, 200, 255, 240)
                        elif k == "face":
                            col = QColor(120, 255, 120, 240)
                        elif k in ("endpoint", "midpoint", "intersection",
                                   "center", "quadrant", "perpendicular",
                                   "tangent", "nearest", "node"):
                            col = QColor(255, 215, 0, 240)
                        else:
                            col = QColor(160, 160, 160, 200)
                        painter.setPen(QPen(col, 2))
                        painter.setBrush(QBrush(QColor(col.red(), col.green(),
                                                       col.blue(), 90)))
                        painter.drawEllipse(QPointF(px, py), 8, 8)
                        painter.setPen(QPen(col, 1))
                        painter.setBrush(Qt.NoBrush)
                        painter.drawEllipse(QPointF(px, py), 12, 12)
                except Exception:
                    traceback.print_exc()

            global _SUN_VECTOR_ACTIVE
            if _SUN_VECTOR_ACTIVE and self._vp is not None:
                sh = _get_shadows(self._mw)
                lat, _ = _get_georef(self._mw)
                az, el = _solar_position(sh, lat)
                az_r, el_r = math.radians(az), math.radians(el)
                dist = _dome_radius()
                if el > 0.5:
                    sx = dist * math.cos(el_r) * math.sin(az_r)
                    sy = dist * math.cos(el_r) * math.cos(az_r)
                    sz = dist * math.sin(el_r)
                    sxr, syr, szr = _rotate_north(sx, sy, sz)
                    c = _get_dome_center()
                    sun = QVector3D(sxr + c.x(), syr + c.y(), szr + c.z())
                    p_o = self._vp.world_to_pixel(c)
                    p_s = self._vp.world_to_pixel(sun)
                    p_p = self._vp.world_to_pixel(
                        QVector3D(sun.x(), sun.y(), c.z()))
                    if p_o is not None and p_s is not None:
                        po = QPointF(float(p_o[0]), float(p_o[1]))
                        ps = QPointF(float(p_s[0]), float(p_s[1]))
                        if p_p is not None:
                            pp = QPointF(float(p_p[0]), float(p_p[1]))
                            painter.setPen(QPen(QColor(180, 180, 180, 200),
                                                1, Qt.DashLine))
                            painter.setBrush(Qt.NoBrush)
                            painter.drawLine(ps, pp)
                            painter.drawLine(pp, po)
                            painter.setPen(QPen(QColor(180, 180, 180, 220), 1))
                            painter.setBrush(QBrush(QColor(180, 180, 180, 180)))
                            painter.drawEllipse(pp, 3, 3)
                        mx, my = self.width() * 0.10, self.height() * 0.10
                        r80 = QRectF(mx, my, self.width() - 2 * mx,
                                     self.height() - 2 * my)
                        tip = ps if r80.contains(ps) else \
                            _clip_segment_to_rect(po, ps, r80)
                        if tip is not None:
                            painter.setPen(QPen(QColor(255, 165, 0, 230), 2))
                            painter.drawLine(po, tip)
                            painter.setBrush(QBrush(QColor(255, 200, 60, 255)))
                            painter.setPen(QPen(QColor(255, 230, 120, 255), 1.5))
                            painter.drawEllipse(tip, 7, 7)
                            painter.setBrush(QBrush(QColor(255, 140, 0, 255)))
                            painter.setPen(QPen(QColor(255, 180, 60, 255), 1))
                            painter.drawEllipse(po, 4, 4)
                            if sh is not None:
                                lbl = f"{int(sh.hour):02d}:{int(sh.minute):02d}"
                                f = painter.font(); f.setPointSize(8); f.setBold(False)
                                painter.setFont(f)
                                painter.setPen(QPen(QColor(60, 60, 60, 240), 1))
                                painter.setBrush(Qt.NoBrush)
                                painter.drawText(
                                    QRectF(tip.x() + 9, tip.y() - 8, 44, 16),
                                    Qt.AlignLeft | Qt.AlignVCenter, lbl)
                            try:
                                f_ang = painter.font()
                                f_ang.setPointSize(8)
                                f_ang.setBold(False)
                                painter.setFont(f_ang)
                                fm_ang = painter.fontMetrics()

                                az_s = f"{az:0.1f}".replace(".", ",")
                                el_s = f"{el:0.1f}".replace(".", ",")
                                txt_az = f"{_t('Az:')} {az_s}°"
                                txt_el = f"{_t('El:')} {el_s}°"

                                painter.setPen(QPen(QColor(230, 60, 60, 240), 1))
                                painter.setBrush(Qt.NoBrush)

                                painter.drawText(
                                    QRectF(po.x() + 10, po.y() + 4, 60, 14),
                                    Qt.AlignLeft | Qt.AlignVCenter, txt_az)

                                painter.drawText(
                                    QRectF(po.x() + 10, po.y() + 18, 60, 14),
                                    Qt.AlignLeft | Qt.AlignVCenter, txt_el)

                            except Exception:
                                traceback.print_exc()
            if not _OVERLAY_VISIBLE:
                return
            radius = self._radius
            c = self._get_center()
            cx, cy = c.x(), c.y()
            painter.setPen(QPen(QColor(160, 160, 160, 200), 1))
            painter.setBrush(QBrush(QColor(30, 30, 30, 140)))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
            painter.setPen(QPen(QColor(220, 220, 220, 230), 1))
            for lbl, ang in (("N", -90), ("E", 0), ("S", 90), ("W", 180)):
                r = math.radians(ang)
                x = cx + math.cos(r) * (radius - 10)
                y = cy + math.sin(r) * (radius - 10)
                painter.drawText(QRectF(x - 8, y - 8, 16, 16),
                                 Qt.AlignCenter, lbl)
            sh = _get_shadows(self._mw)
            lat, lon = _get_georef(self._mw)
            if sh is not None:
                month, day = sh.month, sh.day
                hour, minute = sh.hour, sh.minute
                az, el = _solar_position(sh, lat)
                r = math.radians(az - 90)
                tip_x = cx + math.cos(r) * (radius - 8)
                tip_y = cy + math.sin(r) * (radius - 8)
                painter.setPen(QPen(QColor(255, 200, 60), 2))
                painter.setBrush(QBrush(QColor(255, 200, 60, 220)))
                painter.drawEllipse(QPointF(tip_x, tip_y), 6, 6)
                painter.setPen(QPen(QColor(255, 200, 60, 180), 2))
                painter.drawLine(QPointF(cx, cy), QPointF(tip_x, tip_y))
            else:
                month, day, hour, minute = 10, 12, 9, 56
                az, el = 0.0, 0.0
            w, h = self._info_box_width, self._info_box_height
            bx, by = cx - w / 2, cy + radius + 8
            painter.setPen(QPen(QColor(160, 160, 160, 200), 1))
            painter.setBrush(QBrush(QColor(30, 30, 30, 140)))
            painter.drawRoundedRect(QRectF(bx, by, w, h), 6, 6)
            painter.setPen(QPen(QColor(240, 240, 240, 240), 1))
            f = painter.font(); f.setPointSize(9); painter.setFont(f)
            ds = f"{day:02d}/{month:02d}"
            ts = f"{hour}:{minute:02d}"
            la = f"{lat:.4f}".replace(".", ",")
            lo = f"{lon:.4f}".replace(".", ",")
            aa = f"{az:.1f}".replace(".", ",")
            ee = f"{el:.1f}".replace(".", ",")
            painter.drawText(QRectF(bx, by + 4, w, 16), Qt.AlignCenter,
                             _t("Date: {date}  Time: {time}").format(date=ds, time=ts))
            painter.drawText(QRectF(bx, by + 20, w, 16), Qt.AlignCenter,
                             _t("Lat: {lat}  Lon: {lon}").format(lat=la, lon=lo))
            painter.drawText(QRectF(bx, by + 36, w, 16), Qt.AlignCenter,
                             _t("Azimuth: {az}º  Elevation: {el}º").format(az=aa, el=ee))
            rd, rt = self._slider_rects()

            def _one_slider(rect, lab, frac):
                ty = rect.center().y()
                painter.setPen(QPen(QColor(90, 90, 90, 200), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(QPointF(rect.x(), ty),
                                 QPointF(rect.x() + rect.width(), ty))
                hx = rect.x() + frac * rect.width()
                painter.setPen(QPen(QColor(255, 200, 60, 200), 2))
                painter.drawLine(QPointF(rect.x(), ty), QPointF(hx, ty))
                painter.setPen(QPen(QColor(230, 230, 230, 230), 1))
                painter.setBrush(QBrush(QColor(240, 240, 240, 240)))
                painter.drawEllipse(QPointF(hx, ty),
                                    self._slider_handle_r, self._slider_handle_r)
                painter.setPen(QPen(QColor(220, 220, 220, 230), 1))
                f = painter.font(); f.setPointSize(8); painter.setFont(f)
                painter.drawText(QRectF(rect.x() - 40, ty - 8, 36, 16),
                                 Qt.AlignRight | Qt.AlignVCenter, lab)

            sh_ov = _get_shadows(self._mw)
            if sh_ov is not None:
                try:
                    doy = QDate(2026, int(sh_ov.month),
                                int(sh_ov.day)).dayOfYear()
                except Exception:
                    doy = 80
                _one_slider(rd, _t("Date"), (doy - 1) / 364.0)
                try:
                    mins = int(sh_ov.hour) * 60 + int(sh_ov.minute)
                except Exception:
                    mins = 720
                _one_slider(rt, _t("Time"), mins / 1439.0)
        except Exception:
            traceback.print_exc()
        finally:
            painter.end()


# =========================================================================
# 19. Overlay management
# =========================================================================
def _ensure_overlay(main_window):
    global _OVERLAY
    if _OVERLAY is not None:
        try:
            _ = _OVERLAY.isVisible()
            return _OVERLAY
        except RuntimeError:
            _log("overlay C++ dead; recreating")
            _OVERLAY = None
    vp = _get_viewport(main_window)
    if vp is None:
        return None
    try:
        _OVERLAY = _SunArrowOverlay(vp, main_window)
        return _OVERLAY
    except Exception:
        traceback.print_exc()
        return None


def _update_overlay_mouse_transparency():
    global _OVERLAY
    if _OVERLAY is None:
        return
    try:
        transparent = not _OVERLAY_VISIBLE
        _OVERLAY.setAttribute(Qt.WA_TransparentForMouseEvents, transparent)
    except Exception:
        traceback.print_exc()


def _install_persistent_hover_filter(main_window):
    global _PICK_FILTER, _PICK_FILTER_TARGETS
    vp = _get_viewport(main_window)
    if vp is None:
        return
    if _PICK_FILTER is None:
        _PICK_FILTER = _ViewportPickEventFilter(main_window)
    if vp not in _PICK_FILTER_TARGETS:
        try:
            vp.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(vp)
        except Exception:
            traceback.print_exc()
    ov = _OVERLAY
    if ov is not None and ov not in _PICK_FILTER_TARGETS:
        try:
            ov.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(ov)
        except Exception:
            traceback.print_exc()


def _sync_overlay_visibility(main_window) -> None:
    global _HOVER_CELL_IDX
    if not _needs_overlay_visible():
        if _OVERLAY is not None:
            _OVERLAY.setVisible(False)
        _set_dome_hover_cursor(main_window, False)
        _HOVER_CELL_IDX = -1
        return
    ov = _ensure_overlay(main_window)
    if ov is None:
        return
    ov.setVisible(True)
    ov.raise_()
    _update_overlay_mouse_transparency()
    _install_persistent_hover_filter(main_window)


def _needs_overlay_visible() -> bool:
    return _OVERLAY_VISIBLE or _SUN_VECTOR_ACTIVE or _SUN_DOME_ACTIVE


def _set_overlay_visible(main_window, visible: bool) -> None:
    global _OVERLAY_VISIBLE
    _OVERLAY_VISIBLE = visible
    _sync_overlay_visibility(main_window)

# =========================================================================
# 20.0 — Mini-dialog for PNG export options (opened before QFileDialog)
# =========================================================================
class _ExportPngDialog(QDialog):
    """Small dialog with the PNG export options (transparent background).

    Opens *before* the native QFileDialog, so the user chooses the
    background in the export flow itself, then picks the filename.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Save PNG"))
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self._transparent = bool(_EXPORT_TRANSPARENT_BG)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Header
        lbl_title = QLabel(_t("Export options"))
        f = lbl_title.font()
        f.setBold(True)
        lbl_title.setFont(f)
        lay.addWidget(lbl_title)

        # Transparent-background checkbox
        self._chk_transparent = QCheckBox(_t("Transparent background"))
        self._chk_transparent.setChecked(self._transparent)
        self._chk_transparent.setToolTip(
            _t("If checked, the exported PNG will have a transparent background."))
        lay.addWidget(self._chk_transparent)

        # Hint line
        self._lbl_hint = QLabel(_t("The image will include the viewport and the solar overlay."))
        self._lbl_hint.setWordWrap(True)
        self._lbl_hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self._lbl_hint)

        # Buttons
        bb = QDialogButtonBox(self)
        self._btn_ok = bb.addButton(_t("Continue"), QDialogButtonBox.AcceptRole)
        self._btn_cancel = bb.addButton(_t("Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_accept(self):
        global _EXPORT_TRANSPARENT_BG
        _EXPORT_TRANSPARENT_BG = bool(self._chk_transparent.isChecked())
        # Persist the choice in the scene
        try:
            mw = _discover_main_window()
            if mw is not None:
                _save_state_to_scene(mw)
        except Exception:
            traceback.print_exc()
        self.accept()

    def is_transparent(self) -> bool:
        return bool(self._chk_transparent.isChecked())
        
        
# =========================================================================
# 20. Capture / Export PNG
# =========================================================================
def _capture_viewport_to_png(main_window, file_path: str) -> bool:
    """Captura viewport + overlay. Não engole nada, loga tudo."""
    if main_window is None:
        main_window = _discover_main_window()
    vp = _get_viewport(main_window)
    if vp is None:
        _log(f"capture: viewport not found (main_window={main_window!r})")
        return False

    w = int(vp.width())
    h = int(vp.height())
    if w <= 0 or h <= 0:
        _log(f"capture: viewport has zero size ({w}x{h})")
        return False

    if _EXPORT_TRANSPARENT_BG:
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        ov = _OVERLAY
        if ov is not None and ov.isVisible():
            p = QPainter(img)
            try:
                ov.render(p, QPoint(0, 0))
            finally:
                p.end()
    else:
        pix = QPixmap(w, h)
        pix.fill(Qt.white)
        # Render the 3D viewport without the overlay first, then the overlay
        # exactly once: QWidget.render() also paints child widgets, and the
        # overlay's semi-transparent panels would otherwise be composited
        # twice (looking darker than on screen).
        ov = _OVERLAY
        ov_was_visible = ov is not None and ov.isVisible()
        if ov_was_visible:
            ov.setVisible(False)
        try:
            vp.render(pix)
        finally:
            if ov_was_visible:
                ov.setVisible(True)
        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        if img.isNull():
            _log("capture: image is null after toImage().convertToFormat")
            return False
        if ov is not None and ov.isVisible():
            p = QPainter(img)
            try:
                ov.render(p, QPoint(0, 0))
            finally:
                p.end()

    if img.isNull() or img.width() <= 0 or img.height() <= 0:
        _log(f"capture: refusing to save null/empty image "
             f"(isNull={img.isNull()} w={img.width()} h={img.height()})")
        return False

    path_norm = os.path.normpath(file_path).strip()
    _log(f"capture: saving to {path_norm!r} "
         f"(transparent={_EXPORT_TRANSPARENT_BG}, "
         f"size={img.width()}x{img.height()})")
    ok = img.save(path_norm, "PNG")
    _log(f"capture: img.save({path_norm!r}) -> {ok}")
    return ok
    

def _export_screenshot(main_window) -> None:
    """Mini-dialog + QFileDialog + tentar salvar em vários caminhos."""
    if main_window is None:
        main_window = _discover_main_window()
    if main_window is None:
        QMessageBox.warning(
            None, _t("Save PNG"),
            _t("Could not locate the IngeTrazo main window."))
        return

    # 1. Mini-dialog
    try:
        dlg = _ExportPngDialog(parent=main_window)
        if dlg.exec() != QDialog.Accepted:
            return
    except Exception:
        traceback.print_exc()
        return

    # 2. File dialog
    try:
        default_dir = QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation) or _HERE
        stamp = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        default_name = os.path.join(default_dir, f"sunpath_{stamp}.png")
        path, _flt = QFileDialog.getSaveFileName(
            main_window, _t("Save PNG"), default_name,
            "PNG (*.png);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
    except Exception:
        traceback.print_exc()
        return

    # 3. Capture
    _log(f"export: capturing to {path!r} (transparent={_EXPORT_TRANSPARENT_BG})")
    ok = _capture_viewport_to_png(main_window, path)
    _log(f"export: capture returned {ok}")

    # 4. If the chosen path failed, try the system temporary folder.
    final_path = path
    fallback_used = False
    if not ok:
        try:
            fallback_dir = os.path.join(tempfile.gettempdir(), "igz_sunpath")
            os.makedirs(fallback_dir, exist_ok=True)
            fallback_path = os.path.join(
                fallback_dir,
                os.path.basename(os.path.normpath(path)))
            _log(f"export: trying fallback {fallback_path!r}")
            ok = _capture_viewport_to_png(main_window, fallback_path)
            _log(f"export: fallback capture returned {ok}")
            if ok:
                final_path = fallback_path
                fallback_used = True
        except Exception:
            traceback.print_exc()

    # 5. If it still failed, show a detailed message (do not swallow it).
    if not ok:
        # Diagnóstico visual completo
        details = []
        details.append(f"path = {path}")
        details.append(f"norm  = {os.path.normpath(path)}")
        details.append(f"transparent = {_EXPORT_TRANSPARENT_BG}")
        details.append(f"exists? = {os.path.isfile(path)}")
        details.append(f"writable? = {os.access(os.path.dirname(os.path.normpath(path)), os.W_OK) if os.path.isdir(os.path.dirname(os.path.normpath(path))) else 'dir not found'}")
        msg = _t("Could not save the image to:\n{path}\n\nDetails:\n{details}").format(
            path=path, details="\n".join(details))
        QMessageBox.warning(main_window, _t("Save PNG"), msg)
        return

    # 6. Success
    try:
        sb = main_window.statusBar() if hasattr(main_window, "statusBar") else None
        if sb is not None:
            if fallback_used:
                msg = _t("Image saved (fallback): {path}").format(path=final_path)
            else:
                msg = _t("Image saved: {path}").format(path=final_path)
            sb.showMessage(msg, 6000)
    except Exception:
        pass

    # Mostrar QMessageBox de confirmação para você ter certeza
    try:
        QMessageBox.information(
            main_window, _t("Save PNG"),
            _t("Image saved: {path}").format(path=final_path))
    except Exception:
        pass
        

# =========================================================================
# 21. Calendar / shadows actions
# =========================================================================
class _ShadowsCalendarDialog(QDialog):
    def __init__(self, parent=None, initial_date=None, initial_time=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Calendar"))
        self.resize(250, 250)
        self.setMinimumSize(250, 250)
        self.setSizeGripEnabled(False)
        lay = QVBoxLayout(self)
        self.calendar = QCalendarWidget(self)
        if initial_date:
            self.calendar.setSelectedDate(initial_date)
        lay.addWidget(self.calendar)
        hl = QHBoxLayout()
        hl.addWidget(QLabel(_t("Time") + ":"))
        self.time_edit = QTimeEdit(self)
        self.time_edit.setDisplayFormat("HH:mm")
        if initial_time:
            self.time_edit.setTime(initial_time)
        hl.addWidget(self.time_edit)
        lay.addLayout(hl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def get_date_time(self):
        return self.calendar.selectedDate(), self.time_edit.time()


def _trigger_native_or_toggle_shadows(main_window) -> None:
    sh = _get_shadows(main_window)
    new_state = True
    if sh is not None:
        sh.enabled = not getattr(sh, "enabled", True)
        new_state = sh.enabled
    for action, english, _tt in _LABELED_ACTIONS:
        if english == "Shadows on/off":
            action.blockSignals(True); action.setChecked(new_state)
            action.blockSignals(False); break
    menubar = getattr(main_window, "menuBar", None)
    if callable(menubar):
        bar = menubar()
        if bar is not None:
            for a in bar.findChildren(QAction):
                txt = a.text()
                if any(k in txt.lower() for k in ("shadow", "sombra")):
                    a.trigger(); break
    _repaint(main_window)


def _trigger_calendar(main_window) -> None:
    sh = _get_shadows(main_window)
    init_d = QDate(2026, sh.month, sh.day) if sh else QDate.currentDate()
    init_t = QTime(sh.hour, sh.minute) if sh else QTime(12, 0)
    dlg = _ShadowsCalendarDialog(parent=main_window,
                                 initial_date=init_d, initial_time=init_t)
    if dlg.exec() == QDialog.Accepted:
        sd, st = dlg.get_date_time()
        if sh is not None:
            _shadows_set_date(sh, sd.month(), sd.day())
            _shadows_set_time(sh, st.hour(), st.minute())
        _invalidate_dome_cache()
        if _DIALOG is not None:
            try:
                if hasattr(_DIALOG, "_sld_date"):
                    _DIALOG._sld_date.setValue(sd.dayOfYear())
                if hasattr(_DIALOG, "_sld_time"):
                    _DIALOG._sld_time.setValue(st.hour() * 60 + st.minute())
                if hasattr(_DIALOG, "_refresh_solar_readout"):
                    _DIALOG._refresh_solar_readout()
            except Exception:
                pass
        _repaint(main_window)


# =========================================================================
# 22. Scene / language watchers
# =========================================================================
_LAST_SCENE_ID = None
_LAST_HAS_GEO = None
_LAST_NORTH = None
_LAST_LATLON = None
_LAST_DOME_DATE = None


def _poll_scene_change() -> None:
    global _LAST_SCENE_ID, _LAST_HAS_GEO, _LAST_NORTH, _LAST_LATLON
    global _NORTH_ROTATION_DEG, _LAST_DOME_DATE, _HOVER_CELL_IDX
    mw = _discover_main_window()
    if mw is None:
        return
    sc = _get_scene(mw)
    sid = id(sc) if sc is not None else None
    gr = getattr(sc, "georef", None) if sc is not None else None
    has_geo = gr is not None
    if _LAST_SCENE_ID is None:
        _LAST_SCENE_ID = sid
        _LAST_HAS_GEO = has_geo
        _NORTH_ROTATION_DEG = _read_north_rotation(sc)
        _LAST_NORTH = _NORTH_ROTATION_DEG
        _LAST_LATLON = _get_georef(mw)
        _load_state_from_scene(mw)
        _sync_overlay_visibility(mw)
        return
    if sid != _LAST_SCENE_ID:
        _LAST_SCENE_ID = sid
        _LAST_HAS_GEO = has_geo
        _NORTH_ROTATION_DEG = _read_north_rotation(sc)
        _LAST_NORTH = _NORTH_ROTATION_DEG
        _LAST_LATLON = _get_georef(mw)
        _load_state_from_scene(mw)
        _invalidate_dome_cache()
        _HOVER_CELL_IDX = -1
        _sync_overlay_visibility(mw)
    if has_geo != _LAST_HAS_GEO:
        _LAST_HAS_GEO = has_geo
        _invalidate_dome_cache()
    ll = _get_georef(mw)
    if ll != _LAST_LATLON:
        _LAST_LATLON = ll
        _invalidate_dome_cache()
    sh = _get_shadows(mw)
    if sh is not None:
        cd = (int(sh.month), int(sh.day))
        if cd != _LAST_DOME_DATE:
            _LAST_DOME_DATE = cd
            _invalidate_dome_cache()
    n = _read_north_rotation(sc)
    if abs(n - _NORTH_ROTATION_DEG) > 1e-6:
        _NORTH_ROTATION_DEG = n; _LAST_NORTH = n
        _invalidate_dome_cache()
    if _DIALOG is not None and hasattr(_DIALOG, "_spin_north_cfg"):
        try:
            cur = float(_NORTH_ROTATION_DEG) % 360.0
            spin = _DIALOG._spin_north_cfg
            if abs(spin.value() - cur) > 1e-3:
                spin.blockSignals(True); spin.setValue(cur)
                spin.blockSignals(False)
        except Exception:
            pass
    if _OVERLAY is not None and _OVERLAY.isVisible():
        _OVERLAY.update()


def _scale_to_slider_pos(scale: float) -> int:
    """Converte escala real (0.20–20.0) para posição do QSlider (0–1000),
    usando interpolação logarítmica."""
    import math
    s = max(_DOME_SCALE_MIN, min(_DOME_SCALE_MAX, float(scale)))
    t = (math.log(s) - math.log(_DOME_SCALE_MIN)) / (
        math.log(_DOME_SCALE_MAX) - math.log(_DOME_SCALE_MIN))
    pos = _DOME_SCALE_SLIDER_MIN + int(round(
        t * (_DOME_SCALE_SLIDER_MAX - _DOME_SCALE_SLIDER_MIN)))
    return max(_DOME_SCALE_SLIDER_MIN, min(_DOME_SCALE_SLIDER_MAX, pos))


def _slider_pos_to_scale(pos: int) -> float:
    """Converte posição do QSlider (0–1000) para escala real (0.20–20.0),
    usando interpolação logarítmica."""
    import math
    p = max(_DOME_SCALE_SLIDER_MIN, min(_DOME_SCALE_SLIDER_MAX, int(pos)))
    t = (p - _DOME_SCALE_SLIDER_MIN) / (
        _DOME_SCALE_SLIDER_MAX - _DOME_SCALE_SLIDER_MIN)
    return _DOME_SCALE_MIN * (
        (_DOME_SCALE_MAX / _DOME_SCALE_MIN) ** t)

# =========================================================================
# 23. Set Sun dialog
# =========================================================================
class _SetSunDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self._mw = main_window
        self._labels = []
        self.setWindowTitle(_t("Set Sun"))
        self.setModal(False)
        self.setMinimumWidth(420); self.setMinimumHeight(220)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(8)

        # Date
        db = QWidget(self); dl = QHBoxLayout(db)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(8)
        cd = QLabel(_t("Date")); self._labels.append((cd, "Date"))
        self._lbl_date = QLabel(); self._lbl_date.setMinimumWidth(70)
        self._lbl_date.setAlignment(Qt.AlignCenter)
        self._sld_date = QSlider(Qt.Horizontal)
        self._sld_date.setRange(1, 365); self._sld_date.setMinimumWidth(150)
        sh = _get_shadows(main_window)
        self._sld_date.setValue(
            QDate(2026, sh.month, sh.day).dayOfYear() if sh else 80)
        self._lbl_date.setText(self._date_text(self._sld_date.value()))
        dl.addWidget(cd); dl.addWidget(self._sld_date, 1); dl.addWidget(self._lbl_date)
        lay.addWidget(db)

        # Time
        tb = QWidget(self); tl = QHBoxLayout(tb)
        tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(8)
        ct = QLabel(_t("Time")); self._labels.append((ct, "Time"))
        self._lbl_time = QLabel(); self._lbl_time.setMinimumWidth(70)
        self._lbl_time.setAlignment(Qt.AlignCenter)
        self._sld_time = QSlider(Qt.Horizontal)
        self._sld_time.setRange(0, 1439); self._sld_time.setMinimumWidth(150)
        self._sld_time.setValue(sh.hour * 60 + sh.minute if sh else 720)
        self._lbl_time.setText(self._time_text(self._sld_time.value()))
        tl.addWidget(ct); tl.addWidget(self._sld_time, 1); tl.addWidget(self._lbl_time)
        lay.addWidget(tb)

        # North rotation
        nb = QWidget(self); nl = QHBoxLayout(nb)
        nl.setContentsMargins(0, 0, 0, 0); nl.setSpacing(8)
        cnr = QLabel(_t("North rotation")); self._labels.append((cnr, "North rotation"))
        self._spin_north_cfg = QDoubleSpinBox()
        self._spin_north_cfg.setRange(0.0, 360.0); self._spin_north_cfg.setDecimals(1)
        self._spin_north_cfg.setSingleStep(1.0); self._spin_north_cfg.setSuffix("°")
        self._spin_north_cfg.setMinimumWidth(100)
        sc0 = _get_scene(main_window)
        g0 = getattr(sc0, "georef", None) if sc0 else None
        if g0 is not None and hasattr(g0, "north"):
            try: self._spin_north_cfg.setValue(float(g0.north) % 360.0)
            except Exception: self._spin_north_cfg.setValue(_NORTH_ROTATION_DEG % 360.0)
        else:
            self._spin_north_cfg.setValue(_NORTH_ROTATION_DEG % 360.0)
        nl.addWidget(cnr); nl.addWidget(self._spin_north_cfg); nl.addStretch(1)
        lay.addWidget(nb)

        # Info
        info = QFrame(self); info.setFrameShape(QFrame.StyledPanel)
        il = QHBoxLayout(info); il.setContentsMargins(8, 4, 8, 4); il.setSpacing(16)
        self._lbl_az_cap = QLabel(_t("Azimuth:"))
        self._lbl_az_val = QLabel("0.0°"); self._lbl_az_val.setMinimumWidth(60)
        self._lbl_el_cap = QLabel(_t("Elevation:"))
        self._lbl_el_val = QLabel("0.0°"); self._lbl_el_val.setMinimumWidth(60)
        self._labels.extend([(self._lbl_az_cap, "Azimuth:"),
                             (self._lbl_el_cap, "Elevation:")])
        il.addWidget(self._lbl_az_cap); il.addWidget(self._lbl_az_val)
        il.addStretch(1)
        il.addWidget(self._lbl_el_cap); il.addWidget(self._lbl_el_val)
        lay.addWidget(info)

        # Location
        self._loc_box = QGroupBox(_t("Location"))
        ll = QVBoxLayout(self._loc_box); ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)
        rs = QHBoxLayout()
        self._lbl_source = QLabel(_t("Source"))
        self._combo_source = QComboBox()
        self._combo_source.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._combo_source.setMinimumContentsLength(20)
        for lbl, sid in _MAP_SOURCES:
            self._combo_source.addItem(lbl, sid)
        for i in range(self._combo_source.count()):
            if self._combo_source.itemData(i) == _SELECTED_MAP_SID:
                self._combo_source.setCurrentIndex(i); break
        rs.addWidget(self._lbl_source); rs.addWidget(self._combo_source, 1)
        ll.addLayout(rs)
        rc = QHBoxLayout()
        self._lbl_coords = QLabel(_t("Coords"))
        self._edit_coords = QLineEdit()
        lat0, lon0 = _get_georef(main_window)
        self._edit_coords.setText(f"{lat0:.4f}, {lon0:.4f}")
        self._edit_coords.setMinimumWidth(140)
        self._btn_set_loc = QPushButton()
        self._btn_set_loc.setToolTip(_t("Set Location"))
        ic = _load_themed_icon("sunpath_map", main_window)
        if not ic.isNull():
            self._btn_set_loc.setIcon(ic)
        else:
            self._btn_set_loc.setText("🗺️")
        self._btn_set_loc.setFixedWidth(30)
        self._btn_set_loc.setAutoDefault(False); self._btn_set_loc.setDefault(False)
        self._btn_set_loc.clicked.connect(self._on_open_location_picker)
        self._chk_load_map = QCheckBox(_t("Load map"))
        self._chk_load_map.setChecked(_LOAD_MAP_TOO)
        rc.addWidget(self._lbl_coords); rc.addWidget(self._edit_coords, 1)
        rc.addWidget(self._btn_set_loc); rc.addWidget(self._chk_load_map)
        ll.addLayout(rc)
        lay.addWidget(self._loc_box)

        # Dome
        self._dome_box = QGroupBox(_t("Sun Dome"))
        dl2 = QVBoxLayout(self._dome_box)
        dl2.setContentsMargins(8, 8, 8, 8); dl2.setSpacing(6)
        sr = QHBoxLayout()
        self._lbl_size_cap = QLabel(_t("Diagram size"))
        self._lbl_size_val = QLabel(f"{int(_DOME_DIAGRAM_SCALE * 100)}%")
        self._lbl_size_val.setMinimumWidth(50)
        self._lbl_size_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._sld_size = QSlider(Qt.Horizontal)
        # Slider em escala logarítmica: 20% ↔ 200% ocupa metade do curso,
        # 200% ↔ 2000% ocupa a outra metade. Sensibilidade proporcional
        # ao valor atual — muito melhor que linear para zoom.
        self._sld_size.setRange(_DOME_SCALE_SLIDER_MIN, _DOME_SCALE_SLIDER_MAX)
        self._sld_size.setSingleStep(10)
        self._sld_size.setPageStep(100)
        self._sld_size.setValue(_scale_to_slider_pos(_DOME_DIAGRAM_SCALE))
        sr.addWidget(self._lbl_size_cap); sr.addWidget(self._sld_size, 1)
        sr.addWidget(self._lbl_size_val)
        dl2.addLayout(sr)

        cr = QHBoxLayout()
        self._btn_set_center = QPushButton(_t("Set Center"))
        self._btn_set_center.setAutoDefault(False); self._btn_set_center.setDefault(False)
        self._btn_set_center.clicked.connect(self._trigger_set_center_from_dialog)
        self._lbl_center_cap = QLabel(_t("Center:"))
        c0 = _get_dome_center()
        self._lbl_center_val = QLabel(
            f"{c0.x():.2f}, {c0.y():.2f}, {c0.z():.2f}")
        self._lbl_center_val.setMinimumWidth(120)
        cr.addWidget(self._btn_set_center); cr.addWidget(self._lbl_center_cap)
        cr.addWidget(self._lbl_center_val); cr.addStretch(1)
        dl2.addLayout(cr)

        cr2 = QHBoxLayout(); cr2.setSpacing(10)
        self._chk_analemas = QCheckBox(_t("Analemas"))
        self._chk_analemas.setChecked(_DOME_SHOW_ANALEMAS)
        self._chk_hours = QCheckBox(_t("Hour labels"))
        self._chk_hours.setChecked(_DOME_SHOW_HOUR_LABELS)
        self._chk_dates = QCheckBox(_t("Date labels"))
        self._chk_dates.setChecked(_DOME_SHOW_DATE_LABELS)
        self._chk_compass = QCheckBox(_t("Compass N"))
        self._chk_compass.setChecked(_DOME_SHOW_COMPASS)
        for w in (self._chk_analemas, self._chk_hours, self._chk_dates,
                  self._chk_compass):
            cr2.addWidget(w)
        cr2.addStretch(1)
        dl2.addLayout(cr2)
        lay.addWidget(self._dome_box)

        # Bottom buttons
        br = QHBoxLayout()
        self._btn_toggle_shadows_dlg = QPushButton(_t("Shadows on/off"))
        self._btn_toggle_shadows_dlg.setCheckable(True)
        self._btn_toggle_shadows_dlg.setAutoDefault(False)
        self._btn_toggle_shadows_dlg.setDefault(False)
        if sh is not None:
            self._btn_toggle_shadows_dlg.setChecked(getattr(sh, "enabled", True))
        self._btn_toggle_shadows_dlg.clicked.connect(
            lambda: _trigger_native_or_toggle_shadows(self._mw))
        br.addWidget(self._btn_toggle_shadows_dlg)

        self._btn_toggle_arrow = QPushButton(_t("Sun Arrow"))
        self._btn_toggle_arrow.setCheckable(True)
        self._btn_toggle_arrow.setAutoDefault(False)
        self._btn_toggle_arrow.setDefault(False)
        self._btn_toggle_arrow.setChecked(_OVERLAY_VISIBLE)
        self._btn_toggle_arrow.toggled.connect(self._on_toggle_arrow_dialog)
        br.addWidget(self._btn_toggle_arrow)

        self._btn_toggle_vector = QPushButton(_t("Sun Vector"))
        self._btn_toggle_vector.setCheckable(True)
        self._btn_toggle_vector.setAutoDefault(False)
        self._btn_toggle_vector.setDefault(False)
        self._btn_toggle_vector.setChecked(_SUN_VECTOR_ACTIVE)
        self._btn_toggle_vector.toggled.connect(self._on_toggle_vector_dialog)
        br.addWidget(self._btn_toggle_vector)

        self._btn_toggle_dome = QPushButton(_t("Sun Dome"))
        self._btn_toggle_dome.setCheckable(True)
        self._btn_toggle_dome.setAutoDefault(False)
        self._btn_toggle_dome.setDefault(False)
        self._btn_toggle_dome.setChecked(_SUN_DOME_ACTIVE)
        self._btn_toggle_dome.toggled.connect(self._on_toggle_dome_dialog)
        br.addWidget(self._btn_toggle_dome)

        br.addStretch(1)
        self._btn_close = QPushButton(_t("Close"))
        self._btn_close.setAutoDefault(False); self._btn_close.setDefault(False)
        self._btn_close.clicked.connect(self.close)
        br.addWidget(self._btn_close)
        lay.addLayout(br)

        # Conexões
        self._sld_date.sliderMoved.connect(self._on_date)
        self._sld_date.valueChanged.connect(self._on_date)
        self._sld_time.sliderMoved.connect(self._on_time)
        self._sld_time.valueChanged.connect(self._on_time)
        self._spin_north_cfg.valueChanged.connect(self._on_north_offset_changed)
        self._sld_size.valueChanged.connect(self._on_diagram_size)
        self._chk_analemas.toggled.connect(self._on_toggle_analemas)
        self._chk_hours.toggled.connect(self._on_toggle_hours)
        self._chk_dates.toggled.connect(self._on_toggle_dates)
        self._chk_compass.toggled.connect(self._on_toggle_compass)
        self._combo_source.currentIndexChanged.connect(self._on_source_changed)
        self._edit_coords.editingFinished.connect(self._on_coords_edited)
        self._chk_load_map.stateChanged.connect(self._on_load_map_changed)

        _REFRESH_HOOKS.append(self._retranslate)
        self._refresh_solar_readout()
        self._refresh_dome_controls_visibility()

    def _trigger_set_center_from_dialog(self):
        global _DIALOG_HIDDEN_FOR_PICKING, _DIALOG
        if _DIALOG is not self and _DIALOG is not None:
            _log("DIALOG: órfão, redirecionando para _DIALOG global")
            _DIALOG._trigger_set_center_from_dialog()
            return
        _DIALOG_HIDDEN_FOR_PICKING = True
        self.hide()
        _start_picking_center(self._mw, dialog_to_restore=self)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            fw = QApplication.focusWidget()
            if fw == self._edit_coords:
                self._on_coords_edited(); fw.clearFocus()
                event.accept(); return
            elif fw == self._spin_north_cfg:
                fw.clearFocus(); event.accept(); return
        super().keyPressEvent(event)

    def _refresh_dome_controls_visibility(self):
        self._dome_box.setVisible(_SUN_DOME_ACTIVE)
        self.adjustSize()

    def _on_toggle_arrow_dialog(self, checked):
        _set_overlay_visible(self._mw, checked)
        _save_state_to_scene(self._mw)
        for a, en, _ in _LABELED_ACTIONS:
            if en == "Sun Arrow":
                a.blockSignals(True); a.setChecked(checked)
                a.blockSignals(False)

    def _on_toggle_vector_dialog(self, checked):
        global _SUN_VECTOR_ACTIVE
        _SUN_VECTOR_ACTIVE = checked
        _sync_overlay_visibility(self._mw)
        _save_state_to_scene(self._mw)
        _repaint(self._mw)
        for a, en, _ in _LABELED_ACTIONS:
            if en == "Sun Vector":
                a.blockSignals(True); a.setChecked(checked)
                a.blockSignals(False)

    def _on_toggle_dome_dialog(self, checked):
        global _SUN_DOME_ACTIVE, _HOVER_CELL_IDX
        _SUN_DOME_ACTIVE = checked
        _HOVER_CELL_IDX = -1
        _sync_overlay_visibility(self._mw)
        _save_state_to_scene(self._mw)
        _repaint(self._mw)
        if checked:
            _show_dome_status_message(self._mw)
        self._refresh_dome_controls_visibility()
        for a, en, _ in _LABELED_ACTIONS:
            if en == "Sun Dome":
                a.blockSignals(True); a.setChecked(checked)
                a.blockSignals(False)

    def _on_diagram_size(self, v):
        """Slider mudou: converte posição logarítmica → escala real."""
        global _DOME_DIAGRAM_SCALE
        _DOME_DIAGRAM_SCALE = _slider_pos_to_scale(v)
        # Mostra o valor em % (arredondado).
        self._lbl_size_val.setText(f"{int(round(_DOME_DIAGRAM_SCALE * 100))}%")
        _invalidate_dome_cache()
        _save_state_to_scene(self._mw)
        _repaint(self._mw)

    def _on_toggle_analemas(self, c):
        global _DOME_SHOW_ANALEMAS
        _DOME_SHOW_ANALEMAS = c
        _invalidate_dome_cache()
        _save_state_to_scene(self._mw); _repaint(self._mw)

    def _on_toggle_hours(self, c):
        global _DOME_SHOW_HOUR_LABELS
        _DOME_SHOW_HOUR_LABELS = c
        _save_state_to_scene(self._mw); _repaint(self._mw)

    def _on_toggle_dates(self, c):
        global _DOME_SHOW_DATE_LABELS
        _DOME_SHOW_DATE_LABELS = c
        _save_state_to_scene(self._mw); _repaint(self._mw)

    def _on_toggle_compass(self, c):
        global _DOME_SHOW_COMPASS
        _DOME_SHOW_COMPASS = c
        _save_state_to_scene(self._mw); _repaint(self._mw)


    def _on_north_offset_changed(self, v):
        global _NORTH_ROTATION_DEG
        deg = float(v) % 360.0
        _NORTH_ROTATION_DEG = deg
        sc = _get_scene(self._mw)
        gr = getattr(sc, "georef", None) if sc else None
        if gr is not None and hasattr(gr, "north"):
            try: gr.north = deg
            except Exception: traceback.print_exc()
        _scene_set_attr(sc, "north_rotation_deg", deg)
        try:
            mw = _discover_main_window()
            if mw is not None:
                tray = getattr(mw, "georef_tray", None)
                bm = getattr(tray, "base_map", None) if tray else None
                spin = getattr(bm, "_north", None) if bm else None
                if spin is not None:
                    spin.blockSignals(True); spin.setValue(deg)
                    spin.blockSignals(False)
        except Exception:
            traceback.print_exc()
        _invalidate_dome_cache(); _repaint(self._mw)

    def _on_source_changed(self, idx):
        global _SELECTED_MAP_SID
        sid = self._combo_source.itemData(idx)
        if sid:
            _SELECTED_MAP_SID = sid

    def _on_coords_edited(self):
        try:
            parts = [float(p.strip()) for p in self._edit_coords.text().split(",")]
            if len(parts) == 2:
                _change_location(self._mw, parts[0], parts[1])
        except ValueError:
            pass

    def _on_open_location_picker(self):
        coords = _open_native_georef_dialog(self._mw)
        if coords is not None:
            lat, lon = coords
            self._edit_coords.setText(f"{lat:.6f}, {lon:.6f}")
            _change_location(self._mw, lat, lon)

    def _on_load_map_changed(self, state):
        global _LOAD_MAP_TOO
        try:
            _LOAD_MAP_TOO = (int(state) == int(Qt.Checked))
        except Exception:
            _LOAD_MAP_TOO = bool(state)

    def _date_text(self, doy):
        d = QDate(2026, 1, 1).addDays(doy - 1)
        return f"{d.day():02d} {_months()[d.month() - 1]}"

    def _time_text(self, mn):
        return f"{mn // 60:02d}:{mn % 60:02d}"

    def _refresh_solar_readout(self):
        sh = _get_shadows(self._mw)
        lat, _ = _get_georef(self._mw)
        az, el = _solar_position(sh, lat)
        self._lbl_az_val.setText(f"{az:.1f}°")
        self._lbl_el_val.setText(f"{el:.1f}°")

    def _on_date(self, doy):
        self._lbl_date.setText(self._date_text(doy))
        sh = _get_shadows(self._mw)
        if sh is None: return
        m, d = _day_of_year_to_date(doy)
        _shadows_set_date(sh, m, d)
        _repaint(self._mw); self._refresh_solar_readout()

    def _on_time(self, mn):
        self._lbl_time.setText(self._time_text(mn))
        sh = _get_shadows(self._mw)
        if sh is None: return
        _shadows_set_time(sh, mn // 60, mn % 60)
        _repaint(self._mw); self._refresh_solar_readout()

    def _retranslate(self):
        self.setWindowTitle(_t("Set Sun"))
        self._btn_close.setText(_t("Close"))
        self._btn_toggle_shadows_dlg.setText(_t("Shadows on/off"))
        self._btn_toggle_arrow.setText(_t("Sun Arrow"))
        self._btn_toggle_vector.setText(_t("Sun Vector"))
        self._btn_toggle_dome.setText(_t("Sun Dome"))
        self._loc_box.setTitle(_t("Location"))
        self._dome_box.setTitle(_t("Sun Dome"))
        self._lbl_source.setText(_t("Source"))
        self._lbl_coords.setText(_t("Coords"))
        self._chk_load_map.setText(_t("Load map"))
        self._btn_set_loc.setToolTip(_t("Set Location"))
        self._lbl_size_cap.setText(_t("Diagram size"))
        self._btn_set_center.setText(_t("Set Center"))
        self._lbl_center_cap.setText(_t("Center:"))
        self._chk_analemas.setText(_t("Analemas"))
        self._chk_hours.setText(_t("Hour labels"))
        self._chk_dates.setText(_t("Date labels"))
        self._chk_compass.setText(_t("Compass N"))
        for w, key in self._labels:
            w.setText(_t(key))
        self._lbl_date.setText(self._date_text(self._sld_date.value()))
        self._refresh_solar_readout()


# =========================================================================
# 24. Toolbar / dialog openers
# =========================================================================
def _open_location_picker_from_toolbar(main_window) -> None:
    coords = _open_native_georef_dialog(main_window)
    if coords is None:
        return
    lat, lon = coords
    _change_location(main_window, lat, lon)
    if _DIALOG is not None and hasattr(_DIALOG, "_edit_coords"):
        try:
            _DIALOG._edit_coords.blockSignals(True)
            _DIALOG._edit_coords.setText(f"{lat:.6f}, {lon:.6f}")
            _DIALOG._edit_coords.blockSignals(False)
        except Exception:
            pass
    _invalidate_dome_cache(); _repaint(main_window)


_LABELED_ACTIONS = []
_TOOLBARS = []
_REFRESH_HOOKS = []
_LAST_LANG = None
_LANG_TIMER = None
_DIALOG = None
_TOOLBAR_CREATED = False


def _retranslate() -> None:
    title = _t("Sunpath")
    for tb in _TOOLBARS:
        tb.setWindowTitle(title)
    for a, en, tt in _LABELED_ACTIONS:
        a.setText(_t(en)); a.setToolTip(_t(tt)); a.setStatusTip(_t(tt))
    for h in _REFRESH_HOOKS:
        try: h()
        except Exception: traceback.print_exc()


def _poll_language() -> None:
    global _LAST_LANG
    code = _it_language()
    if code != _LAST_LANG:
        _LAST_LANG = code
        _retranslate()


def _install_language_watcher() -> None:
    global _LANG_TIMER, _LAST_LANG
    if _LANG_TIMER is not None:
        return
    _LAST_LANG = _it_language()
    t = QTimer(); t.setInterval(1000)
    t.timeout.connect(_poll_language); t.start()
    _LANG_TIMER = t


_SCENE_TIMER = None


def _install_scene_watcher() -> None:
    global _SCENE_TIMER
    if _SCENE_TIMER is not None:
        return
    t = QTimer(); t.setInterval(100)
    t.timeout.connect(_poll_scene_change); t.start()
    _SCENE_TIMER = t


def _open_set_sun_dialog(main_window) -> None:
    global _DIALOG, _DIALOG_HIDDEN_FOR_PICKING
    if _DIALOG is not None:
        try:
            _ = _DIALOG.isVisible()
            _DIALOG_HIDDEN_FOR_PICKING = False
            _DIALOG.show(); _DIALOG.raise_(); _DIALOG.activateWindow()
            _DIALOG._refresh_solar_readout()
            return
        except RuntimeError:
            _DIALOG = None
    _DIALOG = _SetSunDialog(main_window, parent=main_window)
    _DIALOG_HIDDEN_FOR_PICKING = False
    _DIALOG.show(); _DIALOG.raise_(); _DIALOG.activateWindow()


def _create_sunpath_toolbar(main_window) -> None:
    global _TOOLBAR_CREATED
    if _TOOLBAR_CREATED:
        return
    if main_window is None or not hasattr(main_window, "addToolBar"):
        return
    try:
        tb = QToolBar(_t("Sunpath"), main_window)
        tb.setObjectName("igz_sunpath")
        tb.setWindowTitle(_t("Sunpath"))
        main_window.addToolBar(Qt.TopToolBarArea, tb)
        _TOOLBARS.append(tb)

        def _add(en_label, tt_key, icon_base, checkable=False,
                 checked=False, handler=None):
            ic = _load_themed_icon(icon_base, main_window)
            a = QAction(ic, _t(en_label), main_window)
            a.setToolTip(_t(tt_key)); a.setStatusTip(_t(tt_key))
            if checkable:
                a.setCheckable(True); a.setChecked(checked)
            if handler is not None:
                if checkable:
                    a.toggled.connect(handler)
                else:
                    a.triggered.connect(handler)
            tb.addAction(a)
            _LABELED_ACTIONS.append((a, en_label, tt_key))
            return a

        sh0 = _get_shadows(main_window)

        # 1. Shadows on/off
        a_sh = _add("Shadows on/off", "Shadows on/off",
                    "sunpath_shadows", checkable=True,
                    checked=getattr(sh0, "enabled", True) if sh0 else True)
        a_sh.toggled.connect(
            lambda c: _trigger_native_or_toggle_shadows(main_window))

        # 2. Sun Arrow
        a_ar = _add("Sun Arrow", "Sun Arrow",
                    "sunpath_arrow", checkable=True, checked=_OVERLAY_VISIBLE)

        def _arrow(c):
            _set_overlay_visible(main_window, c)
            _save_state_to_scene(main_window)
            if _DIALOG is not None and hasattr(_DIALOG, "_btn_toggle_arrow"):
                _DIALOG._btn_toggle_arrow.blockSignals(True)
                _DIALOG._btn_toggle_arrow.setChecked(c)
                _DIALOG._btn_toggle_arrow.blockSignals(False)
        a_ar.toggled.connect(_arrow)

        # 3. Sun Vector
        a_ve = _add("Sun Vector", "Sun Vector",
                    "sunpath_vector", checkable=True,
                    checked=_SUN_VECTOR_ACTIVE)

        def _vec(c):
            global _SUN_VECTOR_ACTIVE
            _SUN_VECTOR_ACTIVE = c
            _sync_overlay_visibility(main_window)
            _save_state_to_scene(main_window); _repaint(main_window)
            if _DIALOG is not None and hasattr(_DIALOG, "_btn_toggle_vector"):
                _DIALOG._btn_toggle_vector.blockSignals(True)
                _DIALOG._btn_toggle_vector.setChecked(c)
                _DIALOG._btn_toggle_vector.blockSignals(False)
        a_ve.toggled.connect(_vec)

        # 4. Sun Dome
        a_do = _add("Sun Dome", "Sun Dome",
                    "sunpath_dome", checkable=True, checked=_SUN_DOME_ACTIVE)

        def _dome(c):
            global _SUN_DOME_ACTIVE, _HOVER_CELL_IDX
            _SUN_DOME_ACTIVE = c
            _HOVER_CELL_IDX = -1
            _sync_overlay_visibility(main_window)
            _save_state_to_scene(main_window); _repaint(main_window)
            if c:
                _show_dome_status_message(main_window)
            if _DIALOG is not None:
                if hasattr(_DIALOG, "_btn_toggle_dome"):
                    _DIALOG._btn_toggle_dome.blockSignals(True)
                    _DIALOG._btn_toggle_dome.setChecked(c)
                    _DIALOG._btn_toggle_dome.blockSignals(False)
                if hasattr(_DIALOG, "_refresh_dome_controls_visibility"):
                    _DIALOG._refresh_dome_controls_visibility()
        a_do.toggled.connect(_dome)

        tb.addSeparator()
        # 5. Set Sun Tool
        _add("Set Sun Tool", "Set Sun Tool", "sunpath_tool",
             handler=lambda: _open_set_sun_dialog(main_window))

        # 6. Set Center
        _add("Set Center", "Set Center", "sunpath_center",
             handler=lambda: _start_picking_center(main_window))

        tb.addSeparator()
        # 7. Calendar
        _add("Calendar", "Calendar", "sunpath_calendar",
             handler=lambda: _trigger_calendar(main_window))

        tb.addSeparator()
        # 8. Set Location
        _add("Set Location", "Set Location", "sunpath_map",
             handler=lambda: _open_location_picker_from_toolbar(main_window))

        tb.addSeparator()
        # 9. Save PNG
        _add("Save PNG", "Save PNG", "sunpath_screenshot",
             handler=lambda: _export_screenshot(main_window))

        tb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        tb.setMaximumWidth(tb.sizeHint().width())

        global _TAB_SHORTCUT
        if _TAB_SHORTCUT is None:
            from PySide6.QtGui import QKeySequence, QShortcut
            _TAB_SHORTCUT = QShortcut(QKeySequence(Qt.Key_Tab), main_window)
            _TAB_SHORTCUT.activated.connect(lambda: _toggle_season_groups(main_window))

        _TOOLBAR_CREATED = True
        _install_language_watcher()
        _install_scene_watcher()
        _log("'Sun Path' toolbar created")
    except Exception:
        traceback.print_exc()


# =========================================================================
# 25. setup()
# =========================================================================
def setup(app):
    print(f"[igz_sunpath] setup(app) — PID={os.getpid()}",
          file=sys.stderr, flush=True)
    _log(f"app: {type(app).__module__}.{type(app).__name__}")

    try:
        for w in QApplication.topLevelWidgets():
            if type(w).__name__ in ("_SetSunDialog", "_ShadowsCalendarDialog",
                                     "_SunArrowOverlay"):
                try:
                    w.close(); w.deleteLater()
                except Exception:
                    pass
    except Exception:
        traceback.print_exc()

    try:
        mw = (_discover_main_window()
              or getattr(app, "main_window", None)
              or getattr(app, "window", None))
        if mw is None:
            QMessageBox.warning(None, _t("Sunpath"),
                                _t("Could not locate the IngeTrazo main window."))
            return
        _create_sunpath_toolbar(mw)
    except Exception:
        traceback.print_exc()