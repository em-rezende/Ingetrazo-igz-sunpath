# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: scene_state.py
# DescriÃ§Ã£o: PersistÃªncia do estado do plugin dentro do .igz.
# =========================================================================
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QApplication

from . import state
from .georef import get_scene, get_viewport
from .dome_geometry import invalidate_dome_cache


def repaint(main_window) -> None:
    vp = get_viewport(main_window)
    if vp is not None and hasattr(vp, "update"):
        vp.update()
    if state._OVERLAY is not None and state._OVERLAY.isVisible():
        state._OVERLAY.update()


def _get_app(main_window):
    """Recupera o app do IngeTrazo."""
    if main_window is not None:
        app = getattr(main_window, "_igz_sunpath_app", None)
        if app is not None:
            return app
    try:
        qapp = QApplication.instance()
        if qapp is not None:
            for w in qapp.topLevelWidgets():
                a = getattr(w, "_igz_sunpath_app", None)
                if a is not None:
                    return a
                if type(w).__name__ == "ExtensionApp":
                    return w
    except Exception:
        pass
    return None


_LOADING = False
_LAST_PAYLOAD = None


def _build_payload() -> dict:
    return {
        "igz_dome_active": bool(state._SUN_DOME_ACTIVE),
        "igz_sun_vector_active": bool(state._SUN_VECTOR_ACTIVE),
        "igz_overlay_visible": bool(state._OVERLAY_VISIBLE),
        "igz_dome_diagram_scale": float(state._DOME_DIAGRAM_SCALE),
        "igz_dome_show_analemas": bool(state._DOME_SHOW_ANALEMAS),
        "igz_dome_show_hour_labels": bool(state._DOME_SHOW_HOUR_LABELS),
        "igz_dome_show_date_labels": bool(state._DOME_SHOW_DATE_LABELS),
        "igz_dome_show_compass": bool(state._DOME_SHOW_COMPASS),
        "igz_export_transparent": bool(state._EXPORT_TRANSPARENT_BG),
        "igz_dome_center": (
            [state._DOME_CENTER_XYZ.x(), state._DOME_CENTER_XYZ.y(),
             state._DOME_CENTER_XYZ.z()]
            if state._DOME_CENTER_XYZ is not None else None
        ),
        "igz_north_rotation_deg": float(state._NORTH_ROTATION_DEG),
    }


def save_state_to_scene(main_window) -> None:
    global _LAST_PAYLOAD
    if _LOADING:                      # nunca salvar durante um load
        return
    app = _get_app(main_window)
    if app is None or not hasattr(app, "set_document_data"):
        return
    payload = _build_payload()
    if payload == _LAST_PAYLOAD:
        return
    try:
        data = app.document_data()
    except Exception:
        data = None
    if not isinstance(data, dict):
        data = {}
    data["igz_sunpath"] = payload
    try:
        app.set_document_data(data)
        _LAST_PAYLOAD = payload
    except Exception:
        import traceback
        traceback.print_exc()


def has_saved_state(main_window) -> bool:
    app = _get_app(main_window)
    try:
        raw = app.document_data() if app is not None else None
    except Exception:
        return False
    return isinstance(raw, dict) and isinstance(raw.get("igz_sunpath"), dict)


def load_state_from_scene(main_window) -> bool:
    """Retorna True se havia dados salvos e eles foram aplicados."""
    global _LOADING, _LAST_PAYLOAD
    app = _get_app(main_window)
    if app is None or not hasattr(app, "document_data"):
        return False
    try:
        raw = app.document_data()
    except Exception:
        return False
    data = raw.get("igz_sunpath") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return False

    _LOADING = True
    try:
        state._SUN_DOME_ACTIVE = bool(data.get("igz_dome_active", False))
        state._SUN_VECTOR_ACTIVE = bool(data.get("igz_sun_vector_active", False))
        state._OVERLAY_VISIBLE = bool(data.get("igz_overlay_visible", False))
        state._DOME_DIAGRAM_SCALE = float(data.get("igz_dome_diagram_scale", 1.0))
        state._DOME_SHOW_ANALEMAS = bool(data.get("igz_dome_show_analemas", True))
        state._DOME_SHOW_HOUR_LABELS = bool(data.get("igz_dome_show_hour_labels", True))
        state._DOME_SHOW_DATE_LABELS = bool(data.get("igz_dome_show_date_labels", True))
        state._DOME_SHOW_COMPASS = bool(data.get("igz_dome_show_compass", True))
        state._EXPORT_TRANSPARENT_BG = bool(data.get("igz_export_transparent", False))
        state._NORTH_ROTATION_DEG = float(data.get("igz_north_rotation_deg", 0.0))
        c = data.get("igz_dome_center")
        state._DOME_CENTER_XYZ = (
            QVector3D(float(c[0]), float(c[1]), float(c[2]))
            if isinstance(c, (list, tuple)) and len(c) == 3 else None
        )
        _LAST_PAYLOAD = _build_payload()
        invalidate_dome_cache()
    finally:
        _LOADING = False
    return True