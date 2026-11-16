# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: shadows.py
# Descrição: Acesso e mutação do objeto scene.shadows.
# =========================================================================
from .georef import get_scene


def get_shadows(main_window):
    sc = get_scene(main_window)
    return getattr(sc, "shadows", None) if sc is not None else None


def set_date(sh, month: int, day: int) -> None:
    sh.month = int(month)
    sh.day = int(day)
    sh.enabled = True


def set_time(sh, hour: int, minute: int) -> None:
    sh.hour = int(hour)
    sh.minute = int(minute)
    sh.enabled = True