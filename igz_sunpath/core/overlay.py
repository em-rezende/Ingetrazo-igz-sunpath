# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: overlay.py
# Descrição: Overlay do domo solar, hover de células e picking do centro.
# =========================================================================
import math
import traceback

from PySide6.QtCore import Qt, QEvent, QPointF, QRectF, QObject
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPalette, QVector3D, QCursor,
    QPixmap, QPolygonF, QFont, QFontMetrics,
)
from PySide6.QtWidgets import QWidget, QApplication

from . import state
from .i18n_loader import _t
from .georef import (
    get_viewport, get_georef, rotate_north, read_north_rotation, get_scene,
)
from .shadows import get_shadows, set_date, set_time
from .solar_math import solar_position, day_of_year_to_date
from .dome_geometry import (
    build_dome_cache, invalidate_dome_cache, get_dome_center,
)
from .scene_state import repaint, save_state_to_scene
from . import capture  # para _discover_main_window


# --- Discover -----------------------------------------------------------
def discover_main_window():
    return capture._discover_main_window()


# --- Status message -----------------------------------------------------
def show_dome_status_message(main_window) -> None:
    try:
        if main_window is not None and hasattr(main_window, "statusBar"):
            sb = main_window.statusBar()
            if sb is not None:
                periodo = (_t("July to December (2nd Semester)")
                           if state._USE_SECOND_HALF_YEAR
                           else _t("January to June (1st Semester)"))
                msg = _t("Sun Dome active | Press TAB to toggle selection "
                         "period (Current: {period})").format(period=periodo)
                sb.showMessage(msg, 7000)
    except Exception:
        traceback.print_exc()


# --- Icons / cursors ----------------------------------------------------
def load_themed_icon(base_name: str, main_window):
    from PySide6.QtGui import QIcon
    icons_dir = state.get_here()
    icons_dir = icons_dir and __import__("os").path.join(icons_dir, "icons")
    import os
    if not icons_dir or not os.path.isdir(icons_dir):
        return QIcon()
    is_dark = True
    try:
        if main_window is not None:
            bg = main_window.palette().color(QPalette.Window)
            is_dark = bg.lightness() < 128
    except Exception:
        pass
    if not is_dark:
        p = os.path.join(icons_dir, f"{base_name}_light.svg")
        if os.path.isfile(p):
            return QIcon(p)
    p = os.path.join(icons_dir, f"{base_name}.svg")
    if os.path.isfile(p):
        return QIcon(p)
    return QIcon()


def load_custom_cursor(base_name: str, main_window) -> QCursor:
    import os
    icons_dir = os.path.join(state.get_here(), "icons")
    if not os.path.isdir(icons_dir):
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
        candidates.append(os.path.join(icons_dir, f"{base_name}_light.svg"))
    candidates.append(os.path.join(icons_dir, f"{base_name}.svg"))
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


# --- Cursor helpers -----------------------------------------------------
_CENTER_CURSOR_APPLIED = False


def set_dome_hover_cursor(main_window, on: bool):
    if state._HOVER_CURSOR_APPLIED == on:
        return
    vp = get_viewport(main_window)
    try:
        if on:
            cur = load_custom_cursor("sunpath_cursor", main_window)
            if vp is not None:
                vp.setCursor(cur)
            if state._OVERLAY is not None and not state._OVERLAY.testAttribute(
                    Qt.WA_TransparentForMouseEvents):
                state._OVERLAY.setCursor(cur)
        else:
            if vp is not None:
                vp.unsetCursor()
            if state._OVERLAY is not None and not state._OVERLAY.testAttribute(
                    Qt.WA_TransparentForMouseEvents):
                state._OVERLAY.unsetCursor()
    except Exception:
        traceback.print_exc()
    state._HOVER_CURSOR_APPLIED = on


def set_center_cursor(main_window, on: bool):
    global _CENTER_CURSOR_APPLIED
    if _CENTER_CURSOR_APPLIED == on:
        return
    vp = get_viewport(main_window)
    try:
        if on:
            cur = load_custom_cursor("sunpath_center", main_window)
            if vp is not None:
                vp.setCursor(cur)
            if state._OVERLAY is not None:
                state._OVERLAY.setCursor(cur)
        else:
            if vp is not None:
                vp.unsetCursor()
            if state._OVERLAY is not None:
                state._OVERLAY.unsetCursor()
    except Exception:
        traceback.print_exc()
    _CENTER_CURSOR_APPLIED = on


# --- Clip (Liang-Barsky) ------------------------------------------------
def clip_segment_to_rect(p0, p1, rect):
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
                if t > t1:
                    return None
                if t > t0:
                    t0 = t
            else:
                if t < t0:
                    return None
                if t < t1:
                    t1 = t
    return QPointF(x0 + t1 * dx, y0 + t1 * dy)


# --- Picking ------------------------------------------------------------
def call_vp_snap(vp, x, y, mods=None):
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


def snap_to_scene_vertex(vp, scene, x, y, tol_px=10.0):
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
                        yield getattr(v, attr)
                        break
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


def pick_with_osnap(vp, x, y, tol_px=12.0):
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

    for fn_name, kind in (("pick_vertex", "vertex"),
                          ("pick_edge", "edge"),
                          ("pick_visible_edge", "edge"),
                          ("edge_point_under_cursor", "edge_point"),
                          ("pick_face", "face"),
                          ("pick_face_any", "face")):
        fn = getattr(vp, fn_name, None)
        if not callable(fn):
            continue
        try:
            res = fn(float(x), float(y))
            if res is None:
                continue
            p = (getattr(res, "point", None)
                 or getattr(res, "position", None)
                 or getattr(res, "co", None)
                 or getattr(res, "closest_point", None)
                 or getattr(res, "hit_point", None))
            if p is not None:
                if not isinstance(p, QVector3D):
                    p = QVector3D(p)
                return p, kind
            if isinstance(res, QVector3D):
                return res, kind
        except Exception:
            traceback.print_exc()

    p = call_vp_snap(vp, x, y)
    if p is not None:
        return p, "snap_at"

    try:
        mw = discover_main_window()
        sc = get_scene(mw) if mw is not None else None
        p = snap_to_scene_vertex(vp, sc, x, y, tol_px)
        if p is not None:
            return p, "vertex_fallback"
    except Exception:
        traceback.print_exc()

    try:
        fn = (getattr(vp, "_world_under_cursor", None)
              or getattr(vp, "_world_from_pixel", None))
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


# --- Uses_snap patch ----------------------------------------------------
_ORIG_USES_SNAP_FOR_PICKING = None
_USES_SNAP_PATCHED = False


def patch_uses_snap_for_picking(vp):
    global _ORIG_USES_SNAP_FOR_PICKING, _USES_SNAP_PATCHED
    if vp is None or _USES_SNAP_PATCHED:
        return
    tool = getattr(vp, "active_tool", None)
    if tool is None:
        return
    try:
        _ORIG_USES_SNAP_FOR_PICKING = getattr(tool, "uses_snap", False)
    except Exception:
        _ORIG_USES_SNAP_FOR_PICKING = False
    try:
        setattr(tool, "uses_snap", True)
        _USES_SNAP_PATCHED = True
    except Exception:
        traceback.print_exc()


def restore_uses_snap_after_picking(vp):
    global _ORIG_USES_SNAP_FOR_PICKING, _USES_SNAP_PATCHED
    if vp is None or not _USES_SNAP_PATCHED:
        return
    tool = getattr(vp, "active_tool", None)
    if tool is not None and _ORIG_USES_SNAP_FOR_PICKING is not None:
        try:
            setattr(tool, "uses_snap", bool(_ORIG_USES_SNAP_FOR_PICKING))
        except Exception:
            traceback.print_exc()
    _ORIG_USES_SNAP_FOR_PICKING = None
    _USES_SNAP_PATCHED = False


# --- Cell helpers -------------------------------------------------------
def project_corners(vp, cell):
    quad = []
    for (x, y, z) in cell["corners"]:
        p = vp.world_to_pixel(QVector3D(x, y, z))
        if p is None:
            return None
        quad.append(QPointF(float(p[0]), float(p[1])))
    return quad


def point_in_quad(px, py, quad):
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


def hover_cell_index(vp, px, py, cache) -> int:
    for k, cell in enumerate(cache.get("cells", [])):
        quad = project_corners(vp, cell)
        if quad is None:
            continue
        if point_in_quad(px, py, quad):
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


def pick_cell_datetime(cell, px, py, quad):
    from PySide6.QtCore import QDate
    b1 = _bary(quad[0], quad[1], quad[2], px, py)
    if b1 is not None and b1[0] >= -1e-6 and b1[1] >= -1e-6 and b1[2] >= -1e-6:
        u, v = b1[0], b1[1]
    else:
        b2 = _bary(quad[0], quad[2], quad[3], px, py)
        if b2 is None:
            return None
        u, v = b2[0], b2[1]

    c00, c10, c11, c01 = quad[0], quad[1], quad[2], quad[3]

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


# --- Overlay widget -----------------------------------------------------
class SunArrowOverlay(QWidget):
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

    def _get_center(self):
        if self._custom_center is not None:
            return self._custom_center
        cx = self.width() - self._margin_right - self._radius
        cy = self._margin_top + self._radius
        return QPointF(max(self._radius, cx), max(self._radius, cy))

    def _info_box_rect(self):
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

    def _hit_slider(self, pos):
        rd, rt = self._slider_rects()
        p = 6
        if rd.adjusted(0, -p, 0, p).contains(pos):
            return "date"
        if rt.adjusted(0, -p, 0, p).contains(pos):
            return "time"
        return None

    def _apply_slider_from_x(self, which, screen_x):
        if self._mw is None:
            return
        rd, rt = self._slider_rects()
        rect = rd if which == "date" else rt
        if rect.width() <= 0:
            return
        t = max(0.0, min(1.0, (screen_x - rect.x()) / rect.width()))
        sh = get_shadows(self._mw)
        if sh is None:
            return
        if which == "date":
            doy = 1 + int(round(t * 364.0))
            m, d = day_of_year_to_date(doy)
            set_date(sh, m, d)
            invalidate_dome_cache()
        else:
            mins = int(round(t * 1439.0))
            set_time(sh, mins // 60, mins % 60)
        if state._DIALOG is not None:
            try:
                if which == "date" and hasattr(state._DIALOG, "_sld_date"):
                    state._DIALOG._sld_date.blockSignals(True)
                    state._DIALOG._sld_date.setValue(doy)
                    state._DIALOG._sld_date.blockSignals(False)
                    if hasattr(state._DIALOG, "_lbl_date"):
                        state._DIALOG._lbl_date.setText(
                            state._DIALOG._date_text(doy))
                elif which == "time" and hasattr(state._DIALOG, "_sld_time"):
                    state._DIALOG._sld_time.blockSignals(True)
                    state._DIALOG._sld_time.setValue(mins)
                    state._DIALOG._sld_time.blockSignals(False)
                    if hasattr(state._DIALOG, "_lbl_time"):
                        state._DIALOG._lbl_time.setText(
                            state._DIALOG._time_text(mins))
                if hasattr(state._DIALOG, "_refresh_solar_readout"):
                    state._DIALOG._refresh_solar_readout()
            except Exception:
                traceback.print_exc()
        repaint(self._mw)

    def mousePressEvent(self, event):
        if state._PICKING_CENTER:
            event.ignore()
            return
        if not state._OVERLAY_VISIBLE:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            pos = event.position()
            hit = self._hit_slider(pos)
            if hit is not None:
                self._drag_slider = hit
                self._apply_slider_from_x(hit, pos.x())
                event.accept()
                return
            c = self._get_center()
            box = self._info_box_rect()
            rect = QRectF(c.x() - self._info_box_width / 2,
                          c.y() - self._radius,
                          self._info_box_width,
                          self._radius * 2 + box.height() + 8)
            if rect.contains(pos):
                self._dragging = True
                self._drag_offset = c - pos
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if state._PICKING_CENTER:
            event.ignore()
            return
        pos = event.position()
        c = self._get_center()
        box = self._info_box_rect()
        info_rect = QRectF(c.x() - self._info_box_width / 2,
                           c.y() - self._radius,
                           self._info_box_width,
                           self._radius * 2 + box.height() + 8)
        if not info_rect.contains(pos) and state._SUN_DOME_ACTIVE:
            vp = self._vp
            if vp is not None:
                lat, _ = get_georef(self._mw)
                sh = get_shadows(self._mw)
                cm = int(sh.month) if sh is not None else 3
                cd = int(sh.day) if sh is not None else 21
                cache = build_dome_cache(state._dome_radius(), lat, cm, cd)
                idx = hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx != state._HOVER_CELL_IDX:
                    state._HOVER_CELL_IDX = idx
                    set_dome_hover_cursor(self._mw, idx >= 0)
                    self.update()
        if self._drag_slider is not None:
            self._apply_slider_from_x(self._drag_slider, pos.x())
            event.accept()
            return
        if getattr(self, "_dragging", False):
            self._custom_center = pos + self._drag_offset
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if state._PICKING_CENTER:
            event.ignore()
            return
        if self._drag_slider is not None:
            self._drag_slider = None
            event.accept()
            return
        if getattr(self, "_dragging", False):
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _ev):
        from .overlay_paint import paint_overlay
        paint_overlay(self)


# --- Pick event filter --------------------------------------------------
class ViewportPickEventFilter(QObject):
    def __init__(self, main_window, dialog_to_restore=None):
        super().__init__()
        self._mw = main_window
        self._dlg = dialog_to_restore

    def _cache_for_current(self):
        lat, _ = get_georef(self._mw)
        sh = get_shadows(self._mw)
        cm = int(sh.month) if sh is not None else 3
        cd = int(sh.day) if sh is not None else 21
        return build_dome_cache(state._dome_radius(), lat, cm, cd)

    def eventFilter(self, obj, ev):
        try:
            if (state._PICKING_CENTER
                    and ((ev.type() == QEvent.KeyPress
                          and ev.key() == Qt.Key_Escape)
                         or (ev.type() == QEvent.MouseButtonPress
                             and ev.button() == Qt.RightButton))):
                state._PICKING_CENTER = False
                for tgt in list(_PICK_FILTER_TARGETS):
                    try:
                        tgt.removeEventFilter(self)
                    except Exception:
                        pass
                _PICK_FILTER_TARGETS.clear()
                restore_uses_snap_after_picking(get_viewport(self._mw))
                set_center_cursor(self._mw, False)
                if state._OVERLAY is not None:
                    try:
                        state._OVERLAY._picking_preview = None
                        state._OVERLAY.update()
                    except Exception:
                        pass
                ev.accept()
                return True

            if state._PICKING_CENTER:
                if ev.type() == QEvent.MouseMove:
                    vp = get_viewport(self._mw)
                    if vp is not None and state._OVERLAY is not None:
                        try:
                            x = float(ev.position().x())
                            y = float(ev.position().y())
                            pt, kind = pick_with_osnap(vp, x, y, 12.0)
                            state._OVERLAY._picking_preview = pt
                            state._OVERLAY._picking_preview_kind = kind
                            state._OVERLAY.update()
                        except Exception:
                            traceback.print_exc()
                    return False

                if (ev.type() == QEvent.MouseButtonPress
                        and ev.button() == Qt.LeftButton):
                    pos = ev.position()
                    vp = get_viewport(self._mw)
                    pt_3d = None
                    if vp is not None:
                        x, y = float(pos.x()), float(pos.y())
                        pt_3d, _kind = pick_with_osnap(vp, x, y, 12.0)

                    if pt_3d is None:
                        pt_3d = QVector3D(0, 0, 0)

                    if isinstance(pt_3d, QVector3D):
                        state._DOME_CENTER_XYZ = pt_3d
                    elif isinstance(pt_3d, (tuple, list)) and len(pt_3d) >= 2:
                        z = float(pt_3d[2]) if len(pt_3d) > 2 else 0.0
                        state._DOME_CENTER_XYZ = QVector3D(
                            float(pt_3d[0]), float(pt_3d[1]), z)

                    state._PICKING_CENTER = False
                    for tgt in list(_PICK_FILTER_TARGETS):
                        try:
                            tgt.removeEventFilter(self)
                        except Exception:
                            pass
                    _PICK_FILTER_TARGETS.clear()
                    restore_uses_snap_after_picking(vp)
                    set_center_cursor(self._mw, False)

                    if state._OVERLAY is not None:
                        try:
                            state._OVERLAY._picking_preview = None
                            state._OVERLAY._picking_preview_kind = "none"
                            state._OVERLAY.update()
                        except Exception:
                            pass

                    invalidate_dome_cache()
                    save_state_to_scene(self._mw)
                    repaint(self._mw)

                    if state._DIALOG is not None and hasattr(
                            state._DIALOG, "_lbl_center_val"):
                        c = get_dome_center()
                        try:
                            state._DIALOG._lbl_center_val.setText(
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

            if not state._SUN_DOME_ACTIVE:
                return False

            if ev.type() == QEvent.MouseMove:
                pos = ev.position()
                vp = get_viewport(self._mw)
                if vp is None:
                    return False
                cache = self._cache_for_current()
                idx = hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx != state._HOVER_CELL_IDX:
                    state._HOVER_CELL_IDX = idx
                    set_dome_hover_cursor(self._mw, idx >= 0)
                    if state._OVERLAY is not None:
                        state._OVERLAY.update()
                return False

            if (ev.type() == QEvent.MouseButtonPress
                    and ev.button() == Qt.LeftButton):
                pos = ev.position()
                vp = get_viewport(self._mw)
                if vp is None:
                    return False
                cache = self._cache_for_current()
                idx = hover_cell_index(vp, pos.x(), pos.y(), cache)
                if idx < 0:
                    return False
                cell = cache["cells"][idx]
                quad = project_corners(vp, cell)
                if quad is None:
                    return False
                res = pick_cell_datetime(cell, pos.x(), pos.y(), quad)
                if res is None:
                    return False
                m, d, h, mi = res
                sh = get_shadows(self._mw)
                if sh is not None:
                    set_date(sh, m, d)
                    set_time(sh, h, mi)
                if state._OVERLAY_VISIBLE:
                    state._OVERLAY_VISIBLE = False
                if not state._SUN_VECTOR_ACTIVE:
                    state._SUN_VECTOR_ACTIVE = True
                if state._DIALOG is not None:
                    try:
                        doy = QDate(2026, m, d).dayOfYear()
                        mins = h * 60 + mi
                        if hasattr(state._DIALOG, "_sld_date"):
                            state._DIALOG._sld_date.blockSignals(True)
                            state._DIALOG._sld_date.setValue(doy)
                            state._DIALOG._sld_date.blockSignals(False)
                        if hasattr(state._DIALOG, "_sld_time"):
                            state._DIALOG._sld_time.blockSignals(True)
                            state._DIALOG._sld_time.setValue(mins)
                            state._DIALOG._sld_time.blockSignals(False)
                        if hasattr(state._DIALOG, "_refresh_solar_readout"):
                            state._DIALOG._refresh_solar_readout()
                    except Exception:
                        traceback.print_exc()
                invalidate_dome_cache()
                save_state_to_scene(self._mw)
                repaint(self._mw)
                ev.accept()
                return True
            return False
        except Exception:
            traceback.print_exc()
            return False


_PICK_FILTER = None
_PICK_FILTER_TARGETS = []


def ensure_overlay(main_window):
    if state._OVERLAY is not None:
        try:
            _ = state._OVERLAY.isVisible()
            return state._OVERLAY
        except RuntimeError:
            state._OVERLAY = None
    vp = get_viewport(main_window)
    if vp is None:
        return None
    try:
        state._OVERLAY = SunArrowOverlay(vp, main_window)
        return state._OVERLAY
    except Exception:
        traceback.print_exc()
        return None


def update_overlay_mouse_transparency():
    if state._OVERLAY is None:
        return
    try:
        transparent = not state._OVERLAY_VISIBLE
        state._OVERLAY.setAttribute(Qt.WA_TransparentForMouseEvents,
                                    transparent)
    except Exception:
        traceback.print_exc()


def install_persistent_hover_filter(main_window):
    global _PICK_FILTER
    vp = get_viewport(main_window)
    if vp is None:
        return
    if _PICK_FILTER is None:
        _PICK_FILTER = ViewportPickEventFilter(main_window)
    if vp not in _PICK_FILTER_TARGETS:
        try:
            vp.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(vp)
        except Exception:
            traceback.print_exc()
    ov = state._OVERLAY
    if ov is not None and ov not in _PICK_FILTER_TARGETS:
        try:
            ov.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(ov)
        except Exception:
            traceback.print_exc()


def sync_overlay_visibility(main_window) -> None:
    if not needs_overlay_visible():
        if state._OVERLAY is not None:
            state._OVERLAY.setVisible(False)
        set_dome_hover_cursor(main_window, False)
        state._HOVER_CELL_IDX = -1
        return
    ov = ensure_overlay(main_window)
    if ov is None:
        return
    ov.setVisible(True)
    ov.raise_()
    update_overlay_mouse_transparency()
    install_persistent_hover_filter(main_window)


def needs_overlay_visible() -> bool:
    return (state._OVERLAY_VISIBLE
            or state._SUN_VECTOR_ACTIVE
            or state._SUN_DOME_ACTIVE)


def set_overlay_visible(main_window, visible: bool) -> None:
    state._OVERLAY_VISIBLE = visible
    sync_overlay_visibility(main_window)


def start_picking_center(main_window, dialog_to_restore=None):
    global _PICK_FILTER
    vp = get_viewport(main_window)
    if vp is None:
        return
    state._PICKING_CENTER = True
    patch_uses_snap_for_picking(vp)
    ensure_overlay(main_window)

    if _PICK_FILTER is None:
        _PICK_FILTER = ViewportPickEventFilter(main_window, dialog_to_restore)
    else:
        _PICK_FILTER._dlg = dialog_to_restore or _PICK_FILTER._dlg
        _PICK_FILTER._mw = main_window

    if vp not in _PICK_FILTER_TARGETS:
        try:
            vp.installEventFilter(_PICK_FILTER)
            _PICK_FILTER_TARGETS.append(vp)
        except Exception:
            traceback.print_exc()

    ov = state._OVERLAY
    if ov is not None:
        try:
            ov._picking_preview = None
            ov._picking_preview_kind = "none"
            ov.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            traceback.print_exc()

    set_center_cursor(main_window, True)