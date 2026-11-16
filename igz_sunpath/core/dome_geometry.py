# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: dome_geometry.py
# Descrição: Geração das meridianas, analemas e células do domo solar.
# =========================================================================
import math

from PySide6.QtCore import QDate
from PySide6.QtGui import QVector3D

from . import state
from .solar_math import solar_position
from .georef import rotate_north

_DOME_CACHE = None


def invalidate_dome_cache():
    global _DOME_CACHE
    _DOME_CACHE = None


def get_dome_center() -> QVector3D:
    return state._DOME_CENTER_XYZ if state._DOME_CENTER_XYZ is not None else QVector3D(0, 0, 0)


def dome_point(az_deg: float, el_deg: float, radius: float):
    ar, er = math.radians(az_deg), math.radians(el_deg)
    x = radius * math.cos(er) * math.sin(ar)
    y = radius * math.cos(er) * math.cos(ar)
    z = radius * math.sin(er)
    rx, ry, rz = rotate_north(x, y, z)
    c = get_dome_center()
    return (rx + c.x(), ry + c.y(), rz + c.z())


def sunrise_sunset_points(date_month_day, radius, lat_deg):
    m, d = date_month_day

    class _S:
        pass

    def _el_at(mn):
        h, mi = mn // 60, mn % 60
        s = _S()
        s.month = m
        s.day = d
        s.hour = h
        s.minute = mi
        try:
            return solar_position(s, lat_deg)
        except Exception:
            return None

    step = 2
    prev = None
    sr_az = None
    ss_az = None
    for mn in range(0, 24 * 60 + 1, step):
        cur = _el_at(mn)
        if cur is None:
            prev = None
            continue
        if prev is not None:
            az0, el0 = prev
            az1, el1 = cur
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
    sr = rotate_north(*sr)
    ss = rotate_north(*ss)
    c = get_dome_center()
    return ((sr[0] + c.x(), sr[1] + c.y(), sr[2] + c.z()),
            (ss[0] + c.x(), ss[1] + c.y(), ss[2] + c.z()))


def build_analemas_cache(radius, lat_deg):
    analemas = []
    for h in state._ANALEMA_HOURS:
        pts = []
        for doy in range(1, 366, state._ANALEMA_DAY_STEP):
            d = QDate(2026, 1, 1).addDays(doy - 1)

            class _S:
                pass

            s = _S()
            s.month = d.month()
            s.day = d.day()
            s.hour = h
            s.minute = 0
            try:
                az, el = solar_position(s, lat_deg)
            except Exception:
                continue
            if el <= 0.0:
                continue
            pts.append(dome_point(az, el, radius))
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


def build_cells(meridians, radius, lat_deg):
    cells = []
    if state._USE_SECOND_HALF_YEAR:
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

    hours = list(state._CELL_HOURS)
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


def build_dome_cache(radius: float, lat_deg: float,
                     current_month: int = 3, current_day: int = 21):
    global _DOME_CACHE
    c = get_dome_center()
    key = (round(radius, 6), round(lat_deg, 6),
           round(state._NORTH_ROTATION_DEG, 6),
           round(c.x(), 4), round(c.y(), 4), round(c.z(), 4),
           state._DOME_SHOW_ANALEMAS, int(current_month), int(current_day))
    if _DOME_CACHE is not None and _DOME_CACHE.get("key") == key:
        return _DOME_CACHE

    warm = {1, 2, 3, 4, 5, 6}
    dates = [(m, 15, False) for m in range(1, 13)]
    dates.append((int(current_month), int(current_day), True))

    meridians = []
    for (m, d, special) in dates:
        pts = []
        marcados = []
        for mn in range(0, 24 * 60, state._DOME_HOUR_STEP_MIN):
            h, mi = mn // 60, mn % 60

            class _S:
                pass

            s = _S()
            s.month = m
            s.day = d
            s.hour = h
            s.minute = mi
            try:
                az, el = solar_position(s, lat_deg)
            except Exception:
                continue
            if el <= 0.0:
                continue
            pts.append(dome_point(az, el, radius))
            if mi == 0 and h in state._DOME_MARKED_HOURS:
                p = dome_point(az, el, radius)
                marcados.append((*p, h))
        if len(pts) < 2:
            continue
        ends = sunrise_sunset_points((m, d), radius, lat_deg)
        nascente, poente = ends if ends else (None, None)
        meridians.append({
            "pts": pts, "marcados": marcados,
            "nascente": nascente, "poente": poente,
            "label": f"{d}/{m}",
            "warm": (m in warm), "special": special,
            "month": m, "day": d,
        })

    analemas = build_analemas_cache(radius, lat_deg) if state._DOME_SHOW_ANALEMAS else []
    cells = build_cells(meridians, radius, lat_deg)

    _DOME_CACHE = {
        "meridians": meridians, "analemas": analemas,
        "cells": cells,
        "radius": radius, "lat": lat_deg, "key": key,
    }
    return _DOME_CACHE