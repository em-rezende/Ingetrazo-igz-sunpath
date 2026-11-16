# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: overlay_paint.py
# Descrição: Pintura do overlay (domo, analemas, vetor solar, info-box).
# =========================================================================
import math
import traceback

from PySide6.QtCore import Qt, QPointF, QRectF, QDate
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QVector3D, QPolygonF

from . import state
from .i18n_loader import _t
from .georef import get_georef, rotate_north
from .shadows import get_shadows
from .solar_math import solar_position
from .dome_geometry import build_dome_cache, get_dome_center
from .overlay import (
    project_corners, clip_segment_to_rect,
)


def paint_overlay(widget) -> None:
    painter = QPainter(widget)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        vp = widget._vp
        if vp is not None and (widget.width() != vp.width()
                               or widget.height() != vp.height()):
            widget._resize_to_parent()

        if state._SUN_DOME_ACTIVE and vp is not None:
            try:
                lat, _ = get_georef(widget._mw)
                sh_d = get_shadows(widget._mw)
                cm, cd = 3, 21
                if sh_d is not None:
                    try:
                        cm, cd = int(sh_d.month), int(sh_d.day)
                    except Exception:
                        pass
                cache = build_dome_cache(state._dome_radius(), lat, cm, cd)
                _draw_compass_xy(widget, painter, state._dome_radius())
                _draw_analemas(widget, painter, cache)
                _draw_dome(widget, painter, cache)
                _draw_hover_cell(widget, painter, cache)
                _draw_hover_cell_labels(widget, painter, cache)

                painter.save()
                f_mode = painter.font()
                f_mode.setPointSize(8)
                f_mode.setBold(True)
                painter.setFont(f_mode)
                painter.setPen(QPen(QColor(40, 90, 220, 230), 1))
                periodo_txt = (_t("Period: Jul-Dec (TAB)")
                               if state._USE_SECOND_HALF_YEAR
                               else _t("Period: Jan-Jun (TAB)"))
                painter.drawText(
                    QRectF(15, widget.height() - 30, 200, 20),
                    Qt.AlignLeft, periodo_txt)
                painter.restore()
            except Exception:
                traceback.print_exc()

        if (state._PICKING_CENTER and vp is not None
                and widget._picking_preview is not None):
            try:
                p = vp.world_to_pixel(widget._picking_preview)
                if p is not None:
                    px, py = float(p[0]), float(p[1])
                    k = getattr(widget, "_picking_preview_kind", "none")
                    if k in ("vertex", "vertex_fallback"):
                        col = QColor(255, 215, 0, 240)
                    elif k in ("edge", "edge_point"):
                        col = QColor(80, 200, 255, 240)
                    elif k == "face":
                        col = QColor(120, 255, 120, 240)
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

        if state._SUN_VECTOR_ACTIVE and vp is not None:
            _draw_sun_vector(widget, painter)

        if not state._OVERLAY_VISIBLE:
            return

        _draw_info_box(widget, painter)
    except Exception:
        traceback.print_exc()
    finally:
        painter.end()


def _draw_compass_xy(widget, painter, radius):
    if widget._vp is None or not state._DOME_SHOW_COMPASS:
        return
    pen_ring = QPen(QColor(140, 220, 140, 200), 1.4)
    pen_tick = QPen(QColor(140, 220, 140, 160), 1)
    c = get_dome_center()
    for r in (radius, radius * 0.9):
        painter.setPen(pen_ring)
        painter.setBrush(Qt.NoBrush)
        prev = None
        for az in range(0, 361, 5):
            ar = math.radians(az)
            x, y = r * math.sin(ar), r * math.cos(ar)
            xr, yr, zr = rotate_north(x, y, 0.0)
            p = widget._vp.world_to_pixel(
                QVector3D(xr + c.x(), yr + c.y(), zr + c.z()))
            if p is not None:
                cur = QPointF(float(p[0]), float(p[1]))
                if prev is not None:
                    painter.drawLine(prev, cur)
                prev = cur
            else:
                prev = None
    painter.setPen(pen_tick)
    for az in range(0, 360, state._DOME_COMPASS_STEP_DEG):
        ar = math.radians(az)
        xi, yi = radius * 0.9 * math.sin(ar), radius * 0.9 * math.cos(ar)
        xo, yo = radius * 1.0 * math.sin(ar), radius * 1.0 * math.cos(ar)
        xir, yir, _ = rotate_north(xi, yi, 0.0)
        xor, yor, _ = rotate_north(xo, yo, 0.0)
        p1 = widget._vp.world_to_pixel(
            QVector3D(xir + c.x(), yir + c.y(), c.z()))
        p2 = widget._vp.world_to_pixel(
            QVector3D(xor + c.x(), yor + c.y(), c.z()))
        if p1 is not None and p2 is not None:
            painter.drawLine(QPointF(float(p1[0]), float(p1[1])),
                             QPointF(float(p2[0]), float(p2[1])))


def _draw_analemas(widget, painter, cache):
    if widget._vp is None:
        return
    painter.setPen(QPen(QColor(140, 140, 140, 200), 1.2))
    painter.setBrush(Qt.NoBrush)
    for an in cache.get("analemas", []):
        prev = None
        for (x, y, z) in an["pts"]:
            p = widget._vp.world_to_pixel(QVector3D(x, y, z))
            if p is not None:
                cur = QPointF(float(p[0]), float(p[1]))
                if prev is not None:
                    painter.drawLine(prev, cur)
                prev = cur
            else:
                prev = None


def _draw_dome(widget, painter, cache):
    if widget._vp is None:
        return
    pen_warm = QPen(QColor(40, 90, 220, 200), 1.4, Qt.SolidLine)
    pen_cold = QPen(QColor(40, 90, 220, 200), 1.4, Qt.DashLine)
    pen_special = QPen(QColor(180, 150, 220, 230), 1.8, Qt.SolidLine)
    pen_pt = QPen(QColor(40, 90, 220, 255), 1)
    brush_pt = QBrush(QColor(40, 90, 220, 255))
    pen_pt_special = QPen(QColor(220, 40, 40, 255), 1)
    brush_pt_special = QBrush(QColor(220, 40, 40, 255))
    f_label = painter.font()
    f_label.setPointSize(7)
    f_label.setBold(False)
    f_hour = painter.font()
    f_hour.setPointSize(7)
    f_hour.setBold(False)

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
            p = widget._vp.world_to_pixel(QVector3D(x, y, z))
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
            p = widget._vp.world_to_pixel(QVector3D(x, y, z))
            if p is None:
                continue
            px, py = float(p[0]), float(p[1])
            painter.drawEllipse(QPointF(px, py), 1.5, 1.5)
            if is_special and state._DOME_SHOW_HOUR_LABELS:
                painter.setFont(f_hour)
                painter.setPen(QPen(QColor(60, 60, 60, 240), 1))
                painter.drawText(QRectF(px + 5, py - 7, 30, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, str(h))
                painter.setPen(pen_pt_local)
                painter.setBrush(brush_pt_local)
        if state._DOME_SHOW_DATE_LABELS:
            painter.setFont(f_label)
            painter.setPen(QPen(QColor(0, 0, 0, 255), 1))
            for key in ("nascente", "poente"):
                p3 = md.get(key)
                if p3 is None:
                    continue
                p = widget._vp.world_to_pixel(QVector3D(*p3))
                if p is not None:
                    painter.drawText(
                        QRectF(float(p[0]) - 20, float(p[1]) - 7, 40, 14),
                        Qt.AlignCenter, md["label"])


def _draw_hover_cell(widget, painter, cache):
    if state._HOVER_CELL_IDX < 0:
        return
    cells = cache.get("cells", [])
    if state._HOVER_CELL_IDX >= len(cells):
        return
    cell = cells[state._HOVER_CELL_IDX]
    quad = project_corners(widget._vp, cell)
    if quad is None:
        return
    poly = QPolygonF(quad)
    painter.setPen(QPen(QColor(255, 215, 0, 240), 2.2))
    painter.setBrush(QBrush(QColor(255, 215, 0, 70)))
    painter.drawPolygon(poly)


def _draw_hover_cell_labels(widget, painter, cache):
    if state._HOVER_CELL_IDX < 0:
        return
    cells = cache.get("cells", [])
    if state._HOVER_CELL_IDX >= len(cells):
        return
    cell = cells[state._HOVER_CELL_IDX]
    quad = project_corners(widget._vp, cell)
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


def _draw_sun_vector(widget, painter):
    vp = widget._vp
    if vp is None:
        return
    sh = get_shadows(widget._mw)
    lat, _ = get_georef(widget._mw)
    az, el = solar_position(sh, lat)
    az_r, el_r = math.radians(az), math.radians(el)
    dist = state._dome_radius()
    if el <= 0.5:
        return
    sx = dist * math.cos(el_r) * math.sin(az_r)
    sy = dist * math.cos(el_r) * math.cos(az_r)
    sz = dist * math.sin(el_r)
    sxr, syr, szr = rotate_north(sx, sy, sz)
    c = get_dome_center()
    sun = QVector3D(sxr + c.x(), syr + c.y(), szr + c.z())
    p_o = vp.world_to_pixel(c)
    p_s = vp.world_to_pixel(sun)
    p_p = vp.world_to_pixel(QVector3D(sun.x(), sun.y(), c.z()))
    if p_o is None or p_s is None:
        return
    po = QPointF(float(p_o[0]), float(p_o[1]))
    ps = QPointF(float(p_s[0]), float(p_s[1]))
    if p_p is not None:
        pp = QPointF(float(p_p[0]), float(p_p[1]))
        painter.setPen(QPen(QColor(180, 180, 180, 200), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(ps, pp)
        painter.drawLine(pp, po)
        painter.setPen(QPen(QColor(180, 180, 180, 220), 1))
        painter.setBrush(QBrush(QColor(180, 180, 180, 180)))
        painter.drawEllipse(pp, 3, 3)
    mx, my = widget.width() * 0.10, widget.height() * 0.10
    r80 = QRectF(mx, my, widget.width() - 2 * mx, widget.height() - 2 * my)
    tip = ps if r80.contains(ps) else clip_segment_to_rect(po, ps, r80)
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
            f = painter.font()
            f.setPointSize(8)
            f.setBold(False)
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
            az_s = f"{az:0.1f}".replace(".", ",")
            el_s = f"{el:0.1f}".replace(".", ",")
            txt_az = f"{_t('Az:')} {az_s}°"
            txt_el = f"{_t('El:')} {el_s}°"
            painter.setPen(QPen(QColor(230, 60, 60, 240), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawText(QRectF(po.x() + 10, po.y() + 4, 60, 14),
                             Qt.AlignLeft | Qt.AlignVCenter, txt_az)
            painter.drawText(QRectF(po.x() + 10, po.y() + 18, 60, 14),
                             Qt.AlignLeft | Qt.AlignVCenter, txt_el)
        except Exception:
            traceback.print_exc()


def _draw_info_box(widget, painter):
    radius = widget._radius
    c = widget._get_center()
    cx, cy = c.x(), c.y()
    painter.setPen(QPen(QColor(160, 160, 160, 200), 1))
    painter.setBrush(QBrush(QColor(30, 30, 30, 140)))
    painter.drawEllipse(QPointF(cx, cy), radius, radius)
    painter.setPen(QPen(QColor(220, 220, 220, 230), 1))
    for lbl, ang in (("N", -90), ("E", 0), ("S", 90), ("W", 180)):
        r = math.radians(ang)
        x = cx + math.cos(r) * (radius - 10)
        y = cy + math.sin(r) * (radius - 10)
        painter.drawText(QRectF(x - 8, y - 8, 16, 16), Qt.AlignCenter, lbl)

    sh = get_shadows(widget._mw)
    lat, lon = get_georef(widget._mw)
    if sh is not None:
        month, day = sh.month, sh.day
        hour, minute = sh.hour, sh.minute
        az, el = solar_position(sh, lat)
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

    w, h = widget._info_box_width, widget._info_box_height
    bx, by = cx - w / 2, cy + radius + 8
    painter.setPen(QPen(QColor(160, 160, 160, 200), 1))
    painter.setBrush(QBrush(QColor(30, 30, 30, 140)))
    painter.drawRoundedRect(QRectF(bx, by, w, h), 6, 6)
    painter.setPen(QPen(QColor(240, 240, 240, 240), 1))
    f = painter.font()
    f.setPointSize(9)
    painter.setFont(f)
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
                     _t("Azimuth: {az}º  Elevation: {el}º").format(az=aa, el=el if False else ee))

    rd, rt = widget._slider_rects()

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
                            widget._slider_handle_r, widget._slider_handle_r)
        painter.setPen(QPen(QColor(220, 220, 220, 230), 1))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(QRectF(rect.x() - 40, ty - 8, 36, 16),
                         Qt.AlignRight | Qt.AlignVCenter, lab)

    sh_ov = get_shadows(widget._mw)
    if sh_ov is not None:
        try:
            doy = QDate(2026, int(sh_ov.month), int(sh_ov.day)).dayOfYear()
        except Exception:
            doy = 80
        _one_slider(rd, _t("Date"), (doy - 1) / 364.0)
        try:
            mins = int(sh_ov.hour) * 60 + int(sh_ov.minute)
        except Exception:
            mins = 720
        _one_slider(rt, _t("Time"), mins / 1439.0)