# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: state.py
# Descrição: Variáveis globais de estado, constantes e helpers básicos.
# =========================================================================
import os
import sys

# --- Caminho do pacote ---------------------------------------------------
_HERE = None


def set_here(path: str):
    global _HERE
    _HERE = path


def get_here() -> str:
    if _HERE:
        return _HERE
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- Debug --------------------------------------------------------------
DEBUG = False


def _log(msg: str) -> None:
    if DEBUG:
        print(f"[igz_sunpath] {msg}", file=sys.stderr, flush=True)


# --- Coordenadas padrão -------------------------------------------------
_LATITUDE_DEG = -19.9167
_LONGITUDE_DEG = -43.9345

# --- Flags de estado ----------------------------------------------------
_SUN_VECTOR_ACTIVE = False
_SUN_DOME_ACTIVE = False
_NORTH_ROTATION_DEG = 0.0
_DOME_CENTER_XYZ = None

_PICKING_CENTER = False
_HOVER_CELL_IDX = -1
_HOVER_CURSOR_APPLIED = False

_DOME_BASE_RADIUS = 5.0
_DOME_DIAGRAM_SCALE = 1.0
_DOME_SCALE_MIN = 0.20
_DOME_SCALE_MAX = 1000.0
_DOME_SCALE_SLIDER_MIN = 0
_DOME_SCALE_SLIDER_MAX = 1000
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

# Referências globais
_OVERLAY = None
_OVERLAY_VISIBLE = False
_DIALOG = None


def _dome_radius():
    return _DOME_BASE_RADIUS * _DOME_DIAGRAM_SCALE


def _scale_to_slider_pos(scale: float) -> int:
    import math
    s = max(_DOME_SCALE_MIN, min(_DOME_SCALE_MAX, float(scale)))
    t = (math.log(s) - math.log(_DOME_SCALE_MIN)) / (
        math.log(_DOME_SCALE_MAX) - math.log(_DOME_SCALE_MIN))
    pos = _DOME_SCALE_SLIDER_MIN + int(round(
        t * (_DOME_SCALE_SLIDER_MAX - _DOME_SCALE_SLIDER_MIN)))
    return max(_DOME_SCALE_SLIDER_MIN, min(_DOME_SCALE_SLIDER_MAX, pos))


def _slider_pos_to_scale(pos: int) -> float:
    import math
    p = max(_DOME_SCALE_SLIDER_MIN, min(_DOME_SCALE_SLIDER_MAX, int(pos)))
    t = (p - _DOME_SCALE_SLIDER_MIN) / (
        _DOME_SCALE_SLIDER_MAX - _DOME_SCALE_SLIDER_MIN)
    return _DOME_SCALE_MIN * ((_DOME_SCALE_MAX / _DOME_SCALE_MIN) ** t)