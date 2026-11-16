# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: georef.py
# Descrição: Leitura/escrita de georef e rotação norte.
# =========================================================================
import math

from . import state


def get_scene(main_window):
    vp = getattr(main_window, "viewport", None)
    return getattr(vp, "scene", None) if vp is not None else None


def get_viewport(main_window):
    return getattr(main_window, "viewport", None)


def scene_get_attr(scene, key, default=None):
    if scene is None:
        return default
    for h in ("attrs", "attributes", "meta"):
        d = getattr(scene, h, None)
        if isinstance(d, dict) and key in d:
            return d[key]
    return getattr(scene, key, default)


def scene_set_attr(scene, key, value) -> bool:
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


def read_georef_from_scene(scene):
    if scene is None:
        return None
    gr = getattr(scene, "georef", None)
    if gr is None:
        return None
    lat = lon = None
    for n in ("lat", "latitude", "lat_deg"):
        v = getattr(gr, n, None)
        if isinstance(v, (int, float)):
            lat = float(v)
            break
    for n in ("lon", "longitude", "lng", "lon_deg"):
        v = getattr(gr, n, None)
        if isinstance(v, (int, float)):
            lon = float(v)
            break
    if lat is not None and lon is not None:
        return (lat, lon)
    return None


def get_georef(main_window):
    r = read_georef_from_scene(get_scene(main_window))
    return r if r is not None else (state._LATITUDE_DEG, state._LONGITUDE_DEG)


def rotate_north(x, y, z):
    if state._NORTH_ROTATION_DEG == 0.0:
        return (x, y, z)
    a = math.radians(-state._NORTH_ROTATION_DEG)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca, z)


def read_north_rotation(scene):
    if scene is None:
        return 0.0
    # 1) atributo real do IngeTrazo
    try:
        v = getattr(scene, "north_deg", None)
        if isinstance(v, (int, float)):
            return _norm_pm180(float(v))
    except Exception:
        pass
    # 2) dict (se o app usar attrs/attributes/meta)
    for h in ("attrs", "attributes", "meta"):
        d = getattr(scene, h, None)
        if isinstance(d, dict) and "north_deg" in d:
            try: return _norm_pm180(float(d["north_deg"]))
            except Exception: pass
    # 3) fallback: georef.north (compat com versões antigas)
    gr = getattr(scene, "georef", None)
    if gr is not None and hasattr(gr, "north"):
        try: return _norm_pm180(float(gr.north))
        except Exception: pass
    return 0.0
        

# =========================================================================
# Norte verdadeiro — delegação ao IngeTrazo
# =========================================================================
def _norm_pm180(deg: float) -> float:
    """Normaliza para a faixa do BaseMapPanel._north: [-180, +180)."""
    d = float(deg) % 360.0
    if d >= 180.0:
        d -= 360.0
    return d


def _norm_pm180(deg: float) -> float:
    d = float(deg) % 360.0
    return d - 360.0 if d >= 180.0 else d


def push_north_to_native(main_window, deg: float) -> float:
    """
    Aplica a rotação do norte no IngeTrazo.

    Bytecode de core.sun.scene_north_deg revelou:
      - se scene.georef existe → lê scene.georef.north
      - senão                 → lê scene.north_deg

    Bytecode de core.sun.turn_sun_to_model revelou:
      - a sombra é girada por scene_north_deg(scene)

    Bytecode de Viewport._shade_factor revelou:
      - vp._LIGHT é cacheado no initializeGL → precisa reescrita manual.
    """
    import traceback
    from PySide6.QtGui import QVector3D
    from PySide6.QtWidgets import QApplication

    deg = _norm_pm180(deg)
    sc = get_scene(main_window)
    vp = get_viewport(main_window)
    if sc is None:
        return deg

    # --- 1) escreve no atributo que o IngeTrazo REALMENTE lê --------
    gr = getattr(sc, "georef", None)
    if gr is not None:
        # cenário A: georef existe → scene.georef.north
        try:
            gr.north = deg
        except Exception:
            traceback.print_exc()
    else:
        # cenário B: georef None → scene.north_deg
        try:
            sc.north_deg = deg
        except Exception:
            traceback.print_exc()
        try:
            scene_set_attr(sc, "north_deg", deg)
        except Exception:
            pass

    # --- 2) espelha no spin nativo (UI do IngeTrazo) ----------------
    try:
        tray = getattr(main_window, "georef_tray", None)
        bm = getattr(tray, "base_map", None) if tray else None
        spin = getattr(bm, "_north", None) if bm else None
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(deg)
            spin.blockSignals(False)
    except Exception:
        traceback.print_exc()

    # --- 3) recalcula _LIGHT (dribla cache de initializeGL) ---------
    try:
        from core.sun import scene_sun_direction
        v = scene_sun_direction(sc)
        if v is not None:
            if isinstance(v, QVector3D):
                vp._LIGHT = v
            elif isinstance(v, (tuple, list)) and len(v) >= 3:
                vp._LIGHT = QVector3D(float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        traceback.print_exc()

    # --- 4) força paintEvent síncrono -------------------------------
    try:
        if vp is not None:
            vp.repaint()
        QApplication.processEvents()
    except Exception:
        traceback.print_exc()

    return deg


def read_north_rotation(scene):
    """Lê o norte do mesmo atributo que o IngeTrazo usa (scene_north_deg)."""
    if scene is None:
        return 0.0
    gr = getattr(scene, "georef", None)
    if gr is not None:
        try:
            v = getattr(gr, "north", 0.0)
            return _norm_pm180(float(v) if v else 0.0)
        except Exception:
            pass
    try:
        v = getattr(scene, "north_deg", 0.0)
        return _norm_pm180(float(v) if v else 0.0)
    except Exception:
        pass
    return 0.0

def read_north_from_native(main_window) -> float:
    """Lê o valor atual do spin nativo (fallback: state)."""
    try:
        tray = getattr(main_window, "georef_tray", None)
        bm = getattr(tray, "base_map", None) if tray else None
        spin = getattr(bm, "_north", None) if bm else None
        if spin is not None:
            return _norm_pm180(float(spin.value()))
    except Exception:
        pass
    return _norm_pm180(float(state._NORTH_ROTATION_DEG))