# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: solar_math.py
# Descrição: Cálculos de posição solar (declinação, equação do tempo, etc.).
# =========================================================================
import math
import traceback

from PySide6.QtCore import QDate

from . import state


def day_of_year_to_date(day_of_year: int):
    d = QDate(2026, 1, 1).addDays(max(1, min(365, day_of_year)) - 1)
    return d.month(), d.day()


def solar_declination_deg(day_of_year: int) -> float:
    return 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))


def equation_of_time_min(day_of_year: int) -> float:
    B = math.radians(360.0 * (day_of_year - 81) / 364.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def solar_position(sh, latitude_deg: float = None):
    if sh is None:
        return 0.0, 0.0
    if latitude_deg is None:
        latitude_deg = state._LATITUDE_DEG
    try:
        d = QDate(2026, int(sh.month), int(sh.day))
        doy = d.dayOfYear()
        decl = math.radians(solar_declination_deg(doy))
        hour_f = float(sh.hour) + float(sh.minute) / 60.0
        hour_f += equation_of_time_min(doy) / 60.0
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
        
def get_sunrise_sunset_hours(month: int, day: int, lat_deg: float):
    """
    Calcula a hora do nascer e do pôr do sol.
    Retorna uma tupla (hora_nascer, minuto_nascer, hora_por, minuto_por).
    Se o sol não nascer ou não se pôr (ex: polos), retorna None.
    """
    import math
    from PySide6.QtCore import QDate
    
    doy = QDate(2026, month, day).dayOfYear()
    decl = math.radians(solar_declination_deg(doy))
    lat = math.radians(lat_deg)
    
    # Ângulo horário para o nascer/pôr do sol (elevação = 0)
    # cos(H) = -tan(lat) * tan(decl)
    cos_h = -math.tan(lat) * math.tan(decl)
    
    if cos_h > 1.0 or cos_h < -1.0:
        return None  # Sol não nasce ou não se põe (noite/polar)
        
    h_angle = math.degrees(math.acos(cos_h))
    
    # Hora solar do nascer e do pôr
    # 12:00 é o meio-dia solar. H_angle é a diferença em graus (15 graus = 1 hora)
    solar_noon_minutes = 12 * 60 + equation_of_time_min(doy)
    sunrise_minutes = solar_noon_minutes - (h_angle / 15.0) * 60
    sunset_minutes = solar_noon_minutes + (h_angle / 15.0) * 60
    
    # Normaliza para o formato de 24h
    sunrise_minutes = sunrise_minutes % 1440
    sunset_minutes = sunset_minutes % 1440
    
    return (
        int(sunrise_minutes // 60), int(sunrise_minutes % 60),
        int(sunset_minutes // 60), int(sunset_minutes % 60)
    )