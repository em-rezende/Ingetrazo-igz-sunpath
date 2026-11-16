# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: panel.py
# Descrição: Diálogo "Set Sun", Painel Lateral e helpers de localização.
# =========================================================================
import math
import os
import traceback

from PySide6.QtCore import Qt, QDate, QTime, QStandardPaths
from PySide6.QtGui import QAction

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QPushButton, QWidget, QFrame, QGroupBox, QCheckBox,
    QDoubleSpinBox, QComboBox, QLineEdit, QCalendarWidget, QTimeEdit,
    QMessageBox, QApplication, QFormLayout, QSizePolicy, QFileDialog,
    QScrollArea, QSpinBox, QAbstractScrollArea,
)

from . import state
from .i18n_loader import _t
from .georef import get_georef, get_scene
from .shadows import get_shadows, set_date, set_time
from .solar_math import solar_position, day_of_year_to_date
from .dome_geometry import (
    get_dome_center, invalidate_dome_cache,
)
from .scene_state import repaint, save_state_to_scene
from .overlay import (
    load_themed_icon, start_picking_center, set_overlay_visible,
    sync_overlay_visibility, show_dome_status_message,
    discover_main_window,
)
from .sun_animator import SunAnimator
from .export_dialog import ExportDialog
from .ffmpeg import _find_ffmpeg, DependencyDialog


# =========================================================================
# Helpers de localização (georef)
# =========================================================================

def _load_map_sources():
    return state._MAP_SOURCES


def _apply_selected_map_source(base_panel) -> None:
    if base_panel is None:
        return
    src = getattr(base_panel, "_source", None)
    if src is None:
        return
    for i in range(src.count()):
        if src.itemData(i) == state._SELECTED_MAP_SID:
            src.setCurrentIndex(i)
            try:
                base_panel._last_sid = state._SELECTED_MAP_SID
            except Exception:
                pass
            return


def _find_base_map_panel(main_window):
    for w in main_window.findChildren(QWidget):
        if type(w).__name__ == "BaseMapPanel":
            return w
    return None


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
        snap = {
            "tile_layer": getattr(sc, "tile_layer", None),
            "terrain": getattr(sc, "terrain", None),
            "photo_mesh": getattr(sc, "photo_mesh", None),
        }
    try:
        btn.click()
    except Exception:
        return None
    if lat_box is None or lon_box is None:
        return None
    try:
        lat, lon = float(lat_box.value()), float(lon_box.value())
    except Exception:
        return None
    if not state._LOAD_MAP_TOO and sc is not None and snap is not None:
        try:
            sc.tile_layer = snap["tile_layer"]
            sc.terrain = snap["terrain"]
            sc.photo_mesh = snap["photo_mesh"]
        except Exception:
            pass
        if vp is not None:
            try:
                vp.update()
            except Exception:
                pass
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _change_location(main_window, lat: float, lon: float) -> None:
    sc = get_scene(main_window)
    if sc is None:
        return
    gr = getattr(sc, "georef", None)
    if gr is not None:
        try:
            gr.lat = float(lat)
        except Exception:
            pass
        try:
            gr.lon = float(lon)
        except Exception:
            pass
    sh = get_shadows(main_window)
    if sh is not None:
        if hasattr(sh, "latitude"):
            sh.latitude = lat
        if hasattr(sh, "longitude"):
            sh.longitude = lon
    try:
        mw = discover_main_window()
        if mw is not None:
            tray = getattr(mw, "georef_tray", None)
            bm = getattr(tray, "base_map", None) if tray else None
            if bm is not None:
                ls = getattr(bm, "_lat", None)
                os_ = getattr(bm, "_lon", None)
                if ls is not None:
                    ls.blockSignals(True)
                    ls.setValue(float(lat))
                    ls.blockSignals(False)
                if os_ is not None:
                    os_.blockSignals(True)
                    os_.setValue(float(lon))
                    os_.blockSignals(False)
    except Exception:
        traceback.print_exc()
    invalidate_dome_cache()
    repaint(main_window)


# =========================================================================
# Diálogo do calendário (independente)
# =========================================================================

class ShadowsCalendarDialog(QDialog):
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

        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def get_date_time(self):
        return self.calendar.selectedDate(), self.time_edit.time()


# =========================================================================
# 1. JANELA FLUTUANTE (SET SUN DIALOG)
# =========================================================================

class SetSunDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self.setWindowTitle(_t("Set Sun"))
        self.setMinimumWidth(380)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self._animator = SunAnimator(main_window)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        sh = get_shadows(main_window)

        # ---------- Data ----------
        db = QWidget(self)
        dl = QHBoxLayout(db)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(8)

        cd = QLabel(_t("Date"))
        self._lbl_date = QLabel()
        self._lbl_date.setMinimumWidth(70)
        self._lbl_date.setAlignment(Qt.AlignCenter)

        self._sld_date = QSlider(Qt.Horizontal)
        self._sld_date.setRange(1, 365)
        self._sld_date.setValue(QDate(2026, sh.month, sh.day).dayOfYear() if sh else 80)
        self._lbl_date.setText(self._date_text(self._sld_date.value()))

        dl.addWidget(cd); dl.addWidget(self._sld_date, 1); dl.addWidget(self._lbl_date)
        lay.addWidget(db)

        # ---------- Hora ----------
        tb = QWidget(self)
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)

        ct = QLabel(_t("Time"))
        self._lbl_time = QLabel()
        self._lbl_time.setMinimumWidth(70)
        self._lbl_time.setAlignment(Qt.AlignCenter)

        self._sld_time = QSlider(Qt.Horizontal)
        self._sld_time.setRange(0, 1439)
        self._sld_time.setValue(sh.hour * 60 + sh.minute if sh else 720)
        self._lbl_time.setText(self._time_text(self._sld_time.value()))

        tl.addWidget(ct); tl.addWidget(self._sld_time, 1); tl.addWidget(self._lbl_time)
        lay.addWidget(tb)

        # ---------- Rotação Norte ----------
        nb = QWidget(self)
        nl = QHBoxLayout(nb)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(8)

        cnr = QLabel(_t("North rotation"))
        self._spin_north_cfg = QDoubleSpinBox()
        self._spin_north_cfg.setRange(0.0, 360.0)
        self._spin_north_cfg.setDecimals(1)
        self._spin_north_cfg.setSingleStep(1.0)
        self._spin_north_cfg.setSuffix("°")
        self._spin_north_cfg.setMinimumWidth(100)

        sc0 = get_scene(main_window)
        g0 = getattr(sc0, "georef", None) if sc0 else None
        if g0 is not None and hasattr(g0, "north"):
            try: self._spin_north_cfg.setValue(float(g0.north) % 360.0)
            except Exception: self._spin_north_cfg.setValue(state._NORTH_ROTATION_DEG % 360.0)
        else:
            self._spin_north_cfg.setValue(state._NORTH_ROTATION_DEG % 360.0)

        nl.addWidget(cnr); nl.addWidget(self._spin_north_cfg); nl.addStretch(1)
        lay.addWidget(nb)

        # ---------- Info (Az/El e Nascer/Pôr) ----------
        info_hl = QHBoxLayout()
        info_hl.setSpacing(8)

        frame_az_el = QFrame(self)
        frame_az_el.setFrameShape(QFrame.StyledPanel)
        il1 = QVBoxLayout(frame_az_el)
        il1.setContentsMargins(8, 4, 8, 4)
        il1.setSpacing(2)

        self._lbl_az_cap = QLabel(_t("Azimuth:"))
        self._lbl_az_val = QLabel("0.0°")
        hl_az = QHBoxLayout()
        hl_az.addWidget(self._lbl_az_cap); hl_az.addWidget(self._lbl_az_val); hl_az.addStretch(1)
        il1.addLayout(hl_az)

        self._lbl_el_cap = QLabel(_t("Elevation:"))
        self._lbl_el_val = QLabel("0.0°")
        hl_el = QHBoxLayout()
        hl_el.addWidget(self._lbl_el_cap); hl_el.addWidget(self._lbl_el_val); hl_el.addStretch(1)
        il1.addLayout(hl_el)

        info_hl.addWidget(frame_az_el, 1)

        frame_sun = QFrame(self)
        frame_sun.setFrameShape(QFrame.StyledPanel)
        il2 = QVBoxLayout(frame_sun)
        il2.setContentsMargins(8, 4, 8, 4)
        il2.setSpacing(2)

        self._lbl_sunrise = QLabel(_t("Sunrise: --:--"))
        il2.addWidget(self._lbl_sunrise)

        self._lbl_sunset = QLabel(_t("Sunset: --:--"))
        il2.addWidget(self._lbl_sunset)

        info_hl.addWidget(frame_sun, 1)

        lay.addLayout(info_hl)

        # ---------- Localização ----------
        self._loc_box = QGroupBox(_t("Location"))
        ll = QVBoxLayout(self._loc_box)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)

        rs = QHBoxLayout()
        self._lbl_source = QLabel(_t("Source"))
        self._combo_source = QComboBox()
        for lbl, sid in state._MAP_SOURCES:
            self._combo_source.addItem(lbl, sid)
        for i in range(self._combo_source.count()):
            if self._combo_source.itemData(i) == state._SELECTED_MAP_SID:
                self._combo_source.setCurrentIndex(i); break
        rs.addWidget(self._lbl_source); rs.addWidget(self._combo_source, 1)
        ll.addLayout(rs)

        rc = QHBoxLayout()
        self._lbl_coords = QLabel(_t("Coords"))
        self._edit_coords = QLineEdit()
        lat0, lon0 = get_georef(main_window)
        self._edit_coords.setText(f"{lat0:.4f}, {lon0:.4f}")
        self._edit_coords.setMinimumWidth(140)

        self._btn_set_loc = QPushButton()
        ic = load_themed_icon("sunpath_map", main_window)
        if not ic.isNull(): self._btn_set_loc.setIcon(ic)
        self._btn_set_loc.setFixedWidth(30)
        self._btn_set_loc.clicked.connect(self._on_open_location_picker)

        self._chk_load_map = QCheckBox(_t("Load map"))
        self._chk_load_map.setChecked(state._LOAD_MAP_TOO)

        rc.addWidget(self._lbl_coords); rc.addWidget(self._edit_coords, 1)
        rc.addWidget(self._btn_set_loc); rc.addWidget(self._chk_load_map)
        ll.addLayout(rc)
        lay.addWidget(self._loc_box)

        # ---------- Domo ----------
        self._dome_box = QGroupBox(_t("Sun Dome"))
        dl2 = QVBoxLayout(self._dome_box)
        dl2.setContentsMargins(8, 8, 8, 8)
        dl2.setSpacing(6)

        sr = QHBoxLayout()
        self._lbl_size_cap = QLabel(_t("Diagram size"))
        self._lbl_size_val = QLabel(f"{int(state._DOME_DIAGRAM_SCALE * 100)}%")
        self._sld_size = QSlider(Qt.Horizontal)
        self._sld_size.setRange(state._DOME_SCALE_SLIDER_MIN, state._DOME_SCALE_SLIDER_MAX)
        self._sld_size.setValue(state._scale_to_slider_pos(state._DOME_DIAGRAM_SCALE))
        sr.addWidget(self._lbl_size_cap); sr.addWidget(self._sld_size, 1); sr.addWidget(self._lbl_size_val)
        dl2.addLayout(sr)

        cr = QHBoxLayout()
        self._btn_set_center = QPushButton(_t("Set Center"))
        self._btn_set_center.clicked.connect(self._trigger_set_center_from_dialog)
        self._lbl_center_cap = QLabel(_t("Center:"))
        c0 = get_dome_center()
        self._lbl_center_val = QLabel(f"{c0.x():.2f}, {c0.y():.2f}, {c0.z():.2f}")
        cr.addWidget(self._btn_set_center); cr.addWidget(self._lbl_center_cap); cr.addWidget(self._lbl_center_val)
        cr.addStretch(1)
        dl2.addLayout(cr)

        cr2 = QHBoxLayout()
        self._chk_analemas = QCheckBox(_t("Analemas"))
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours = QCheckBox(_t("Hour labels"))
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates = QCheckBox(_t("Date labels"))
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass = QCheckBox(_t("Compass N"))
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        for w in (self._chk_analemas, self._chk_hours, self._chk_dates, self._chk_compass):
            cr2.addWidget(w)
        cr2.addStretch(1)
        dl2.addLayout(cr2)
        lay.addWidget(self._dome_box)

        # ---------- Botões do Domo ----------
        br = QHBoxLayout()
        self._btn_toggle_shadows_dlg = QPushButton(_t("Shadows on/off"))
        self._btn_toggle_shadows_dlg.setCheckable(True)
        if sh is not None: self._btn_toggle_shadows_dlg.setChecked(getattr(sh, "enabled", True))
        self._btn_toggle_shadows_dlg.clicked.connect(lambda: _trigger_native_or_toggle_shadows(self._mw))
        br.addWidget(self._btn_toggle_shadows_dlg)

        self._btn_toggle_arrow = QPushButton(_t("Sun Arrow"))
        self._btn_toggle_arrow.setCheckable(True)
        self._btn_toggle_arrow.setChecked(state._OVERLAY_VISIBLE)
        self._btn_toggle_arrow.toggled.connect(self._on_toggle_arrow_dialog)
        br.addWidget(self._btn_toggle_arrow)

        self._btn_toggle_vector = QPushButton(_t("Sun Vector"))
        self._btn_toggle_vector.setCheckable(True)
        self._btn_toggle_vector.setChecked(state._SUN_VECTOR_ACTIVE)
        self._btn_toggle_vector.toggled.connect(self._on_toggle_vector_dialog)
        br.addWidget(self._btn_toggle_vector)

        self._btn_toggle_dome = QPushButton(_t("Sun Dome"))
        self._btn_toggle_dome.setCheckable(True)
        self._btn_toggle_dome.setChecked(state._SUN_DOME_ACTIVE)
        self._btn_toggle_dome.toggled.connect(self._on_toggle_dome_dialog)
        br.addWidget(self._btn_toggle_dome)
        br.addStretch(1)
        lay.addLayout(br)

        # ---------- Animação do Sol ----------
        anim_box = QGroupBox(_t("Sun Animation"))
        anim_layout = QFormLayout(anim_box)

        self._combo_step = QComboBox()
        for m in (60, 30, 15, 10, 5, 1):
            self._combo_step.addItem(_t("{n} min/step").replace("{n}", str(m)), m)
        self._combo_step.setCurrentIndex(1)
        self._combo_step.currentIndexChanged.connect(self._on_step_changed)
        anim_layout.addRow(_t("Step per frame:"), self._combo_step)

        hl_anim_btns = QHBoxLayout()
        self._btn_play = QPushButton(_t("Play"))
        self._btn_play.setCheckable(True)
        self._btn_play.clicked.connect(self._on_play)
        hl_anim_btns.addWidget(self._btn_play)

        self._btn_stop = QPushButton(_t("Stop"))
        self._btn_stop.setCheckable(True)
        self._btn_stop.setChecked(True)
        self._btn_stop.clicked.connect(self._on_stop)
        hl_anim_btns.addWidget(self._btn_stop)

        holder = QWidget()
        holder.setLayout(hl_anim_btns)
        anim_layout.addRow("", holder)
        lay.addWidget(anim_box)

        # ---------- Botão Fechar ----------
        br_close = QHBoxLayout()
        self._btn_close = QPushButton(_t("Close"))
        self._btn_close.clicked.connect(self.close)
        br_close.addStretch(1)
        br_close.addWidget(self._btn_close)
        lay.addLayout(br_close)

        # ---------- Conexões ----------
        self._sld_date.valueChanged.connect(self._on_date)
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

        self._refresh_solar_readout()
        self._refresh_dome_controls_visibility()
        self.sync_dome_checkboxes()

    # --- Animação ---
    def _on_step_changed(self, idx):
        minutes = self._combo_step.itemData(idx)
        if minutes:
            self._animator.set_step_minutes(minutes)

    def _on_play(self):
        self._animator.play()
        self._btn_play.setChecked(True)
        self._btn_stop.setChecked(False)

    def _on_stop(self):
        self._animator.stop()
        self._btn_play.setChecked(False)
        self._btn_stop.setChecked(True)

    def sync_dome_checkboxes(self):
        self._chk_analemas.blockSignals(True)
        self._chk_hours.blockSignals(True)
        self._chk_dates.blockSignals(True)
        self._chk_compass.blockSignals(True)
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        self._chk_analemas.blockSignals(False)
        self._chk_hours.blockSignals(False)
        self._chk_dates.blockSignals(False)
        self._chk_compass.blockSignals(False)

    def _trigger_set_center_from_dialog(self):
        state._DIALOG_HIDDEN_FOR_PICKING = True
        self.hide()
        start_picking_center(self._mw, dialog_to_restore=self)

    def _refresh_dome_controls_visibility(self):
        self._dome_box.setVisible(state._SUN_DOME_ACTIVE)
        self.adjustSize()

    def _on_toggle_arrow_dialog(self, checked):
        state._OVERLAY_VISIBLE = checked
        set_overlay_visible(self._mw, checked)
        save_state_to_scene(self._mw)

    def _on_toggle_vector_dialog(self, checked):
        state._SUN_VECTOR_ACTIVE = checked
        sync_overlay_visibility(self._mw)
        save_state_to_scene(self._mw)
        repaint(self._mw)

    def _on_toggle_dome_dialog(self, checked):
        state._SUN_DOME_ACTIVE = checked
        state._HOVER_CELL_IDX = -1
        sync_overlay_visibility(self._mw)
        save_state_to_scene(self._mw)
        repaint(self._mw)
        if checked: show_dome_status_message(self._mw)
        self._refresh_dome_controls_visibility()
        self.sync_dome_checkboxes()

    def _on_diagram_size(self, v):
        state._DOME_DIAGRAM_SCALE = state._slider_pos_to_scale(v)
        self._lbl_size_val.setText(f"{int(round(state._DOME_DIAGRAM_SCALE * 100))}%")
        invalidate_dome_cache()
        save_state_to_scene(self._mw)
        repaint(self._mw)

    def _on_toggle_analemas(self, c):
        state._DOME_SHOW_ANALEMAS = c
        invalidate_dome_cache()
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_hours(self, c):
        state._DOME_SHOW_HOUR_LABELS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_dates(self, c):
        state._DOME_SHOW_DATE_LABELS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_compass(self, c):
        state._DOME_SHOW_COMPASS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_north_offset_changed(self, v):
        from .georef import push_north_to_native, scene_set_attr
        deg = push_north_to_native(self._mw, float(v))
        state._NORTH_ROTATION_DEG = deg
        # O push_north_to_native já gravou no atributo correto;
        # não reescrever para evitar inconsistência entre georef e north_deg.
        invalidate_dome_cache()
        save_state_to_scene(self._mw)
        repaint(self._mw)
        
    def _on_source_changed(self, idx):
        sid = self._combo_source.itemData(idx)
        if sid: state._SELECTED_MAP_SID = sid

    def _on_coords_edited(self):
        try:
            parts = [float(p.strip()) for p in self._edit_coords.text().split(",")]
            if len(parts) == 2: _change_location(self._mw, parts[0], parts[1])
        except ValueError: pass

    def _on_open_location_picker(self):
        coords = _open_native_georef_dialog(self._mw)
        if coords is not None:
            lat, lon = coords
            self._edit_coords.setText(f"{lat:.6f}, {lon:.6f}")
            _change_location(self._mw, lat, lon)

    def _on_load_map_changed(self, state_val):
        try: state._LOAD_MAP_TOO = (int(state_val) == int(Qt.Checked))
        except Exception: state._LOAD_MAP_TOO = bool(state_val)

    def _date_text(self, doy):
        d = QDate(2026, 1, 1).addDays(doy - 1)
        from .i18n_loader import _months
        return f"{d.day():02d} {_months()[d.month() - 1]}"

    def _time_text(self, mn): return f"{mn // 60:02d}:{mn % 60:02d}"

    def _refresh_solar_readout(self):
        sh = get_shadows(self._mw)
        lat, _ = get_georef(self._mw)
        az, el = solar_position(sh, lat)
        self._lbl_az_val.setText(f"{az:.1f}°")
        self._lbl_el_val.setText(f"{el:.1f}°")

        if sh is not None:
            from .solar_math import get_sunrise_sunset_hours
            horas = get_sunrise_sunset_hours(sh.month, sh.day, lat)
            if horas:
                h_sr, m_sr, h_ss, m_ss = horas
                self._lbl_sunrise.setText(_t("Sunrise: {h:02d}:{m:02d}").format(h=h_sr, m=m_sr))
                self._lbl_sunset.setText(_t("Sunset: {h:02d}:{m:02d}").format(h=h_ss, m=m_ss))
            else:
                self._lbl_sunrise.setText(_t("Sunrise: --:--"))
                self._lbl_sunset.setText(_t("Sunset: --:--"))

    def _on_date(self, doy):
        self._lbl_date.setText(self._date_text(doy))
        sh = get_shadows(self._mw)
        if sh:
            m, d = day_of_year_to_date(doy)
            set_date(sh, m, d)
            repaint(self._mw)
            self._refresh_solar_readout()

    def _on_time(self, mn):
        self._lbl_time.setText(self._time_text(mn))
        sh = get_shadows(self._mw)
        if sh:
            set_time(sh, mn // 60, mn % 60)
            repaint(self._mw)
            self._refresh_solar_readout()

    def closeEvent(self, event):
        if hasattr(self, "_animator"):
            self._animator.stop()
        super().closeEvent(event)

    def sync_ui_from_state(self):
        self._sld_size.blockSignals(True)
        self._sld_size.setValue(state._scale_to_slider_pos(state._DOME_DIAGRAM_SCALE))
        self._sld_size.blockSignals(False)
        self._lbl_size_val.setText(f"{int(round(state._DOME_DIAGRAM_SCALE * 100))}%")

        self._spin_north_cfg.blockSignals(True)
        self._spin_north_cfg.setValue(state._NORTH_ROTATION_DEG)
        self._spin_north_cfg.blockSignals(False)

        self._chk_analemas.blockSignals(True)
        self._chk_hours.blockSignals(True)
        self._chk_dates.blockSignals(True)
        self._chk_compass.blockSignals(True)
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        self._chk_analemas.blockSignals(False)
        self._chk_hours.blockSignals(False)
        self._chk_dates.blockSignals(False)
        self._chk_compass.blockSignals(False)

        self._btn_toggle_arrow.blockSignals(True)
        self._btn_toggle_vector.blockSignals(True)
        self._btn_toggle_dome.blockSignals(True)
        self._btn_toggle_arrow.setChecked(state._OVERLAY_VISIBLE)
        self._btn_toggle_vector.setChecked(state._SUN_VECTOR_ACTIVE)
        self._btn_toggle_dome.setChecked(state._SUN_DOME_ACTIVE)
        self._btn_toggle_arrow.blockSignals(False)
        self._btn_toggle_vector.blockSignals(False)
        self._btn_toggle_dome.blockSignals(False)

        from .dome_geometry import get_dome_center
        c = get_dome_center()
        self._lbl_center_val.setText(f"{c.x():.2f}, {c.y():.2f}, {c.z():.2f}")

        self._refresh_dome_controls_visibility()


# =========================================================================
# 2. PAINEL LATERAL (SUN PATH PANEL)
# =========================================================================
class SunPathPanel(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumWidth(1)

        self._animator = SunAnimator(main_window)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMinimumWidth(0)
        try:
            scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        except Exception:
            pass

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        container.setMinimumWidth(0)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        sh = get_shadows(main_window)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # --- Data ---
        self._lbl_date = QLabel()
        self._lbl_date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._sld_date = QSlider(Qt.Horizontal)
        self._sld_date.setRange(1, 365)
        self._sld_date.setValue(QDate(2026, sh.month, sh.day).dayOfYear() if sh else 80)
        self._lbl_date.setText(self._date_text(self._sld_date.value()))

        date_holder = QWidget()
        date_holder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl_date = QHBoxLayout(date_holder)
        hl_date.setContentsMargins(0, 0, 0, 0)
        hl_date.addWidget(self._sld_date, 1)
        hl_date.addWidget(self._lbl_date)
        form.addRow(_t("Date") + ":", date_holder)

        # --- Hora ---
        self._lbl_time = QLabel()
        self._lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._sld_time = QSlider(Qt.Horizontal)
        self._sld_time.setRange(0, 1439)
        self._sld_time.setValue(sh.hour * 60 + sh.minute if sh else 720)
        self._sld_time.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lbl_time.setText(self._time_text(self._sld_time.value()))
        hl_time = QHBoxLayout()
        hl_time.addWidget(self._sld_time, 1)
        hl_time.addWidget(self._lbl_time)
        form.addRow(_t("Time") + ":", hl_time)

        # --- Rotação Norte ---
        self._spin_north_cfg = QDoubleSpinBox()
        self._spin_north_cfg.setRange(0.0, 360.0)
        self._spin_north_cfg.setDecimals(1)
        self._spin_north_cfg.setSuffix("°")
        self._spin_north_cfg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sc0 = get_scene(main_window)
        g0 = getattr(sc0, "georef", None) if sc0 else None
        if g0 is not None and hasattr(g0, "north"):
            try: self._spin_north_cfg.setValue(float(g0.north) % 360.0)
            except Exception: pass
        form.addRow(_t("North rotation") + ":", self._spin_north_cfg)

        lay.addLayout(form)

        # --- Info Az/El ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        frame_az_el = QFrame()
        frame_az_el.setFrameShape(QFrame.StyledPanel)
        il1 = QVBoxLayout(frame_az_el)
        il1.setContentsMargins(8, 4, 8, 4)
        il1.setSpacing(2)
        self._lbl_az_val = QLabel("0.0°")
        self._lbl_el_val = QLabel("0.0°")
        self._lbl_az_cap = QLabel(_t("Azimuth:"))
        self._lbl_el_cap = QLabel(_t("Elevation:"))
        hl_az = QHBoxLayout()
        hl_az.addWidget(self._lbl_az_cap); hl_az.addWidget(self._lbl_az_val); hl_az.addStretch(1)
        il1.addLayout(hl_az)
        hl_el = QHBoxLayout()
        hl_el.addWidget(self._lbl_el_cap); hl_el.addWidget(self._lbl_el_val); hl_el.addStretch(1)
        il1.addLayout(hl_el)
        info_layout.addWidget(frame_az_el)

        frame_sun = QFrame()
        frame_sun.setFrameShape(QFrame.StyledPanel)
        il2 = QVBoxLayout(frame_sun)
        il2.setContentsMargins(8, 4, 8, 4)
        il2.setSpacing(2)
        self._lbl_sunrise = QLabel(_t("Sunrise: --:--"))
        il2.addWidget(self._lbl_sunrise)
        self._lbl_sunset = QLabel(_t("Sunset: --:--"))
        il2.addWidget(self._lbl_sunset)
        info_layout.addWidget(frame_sun)
        lay.addLayout(info_layout)

        # --- Localização ---
        self._loc_box = QGroupBox(_t("Location"))
        self._loc_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._loc_box.setMinimumWidth(0)
        ll = QFormLayout(self._loc_box)
        ll.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        ll.setRowWrapPolicy(QFormLayout.DontWrapRows)
        ll.setHorizontalSpacing(8)
        ll.setVerticalSpacing(6)

        self._combo_source = QComboBox()
        self._combo_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for lbl, sid in state._MAP_SOURCES:
            self._combo_source.addItem(lbl, sid)
        ll.addRow(_t("Source") + ":", self._combo_source)

        rc = QHBoxLayout()
        self._edit_coords = QLineEdit()
        self._edit_coords.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lat0, lon0 = get_georef(main_window)
        self._edit_coords.setText(f"{lat0:.4f}, {lon0:.4f}")
        self._btn_set_loc = QPushButton()
        self._btn_set_loc.setToolTip(_t("Set Location"))
        self._btn_set_loc.setFixedWidth(30)
        ic = load_themed_icon("sunpath_map", main_window)
        if not ic.isNull(): self._btn_set_loc.setIcon(ic)
        else: self._btn_set_loc.setText("M")
        self._btn_set_loc.clicked.connect(self._on_open_location_picker)
        rc.addWidget(self._edit_coords, 1)
        rc.addWidget(self._btn_set_loc)
        ll.addRow(_t("Coords") + ":", rc)

        self._chk_load_map = QCheckBox(_t("Load map"))
        ll.addRow("", self._chk_load_map)
        lay.addWidget(self._loc_box)

        # --- Domo ---
        self._dome_box = QGroupBox(_t("Sun Dome"))
        self._dome_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._dome_box.setMinimumWidth(0)
        dl2 = QFormLayout(self._dome_box)
        dl2.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        dl2.setRowWrapPolicy(QFormLayout.DontWrapRows)
        dl2.setHorizontalSpacing(8)
        dl2.setVerticalSpacing(6)

        self._sld_size = QSlider(Qt.Horizontal)
        self._sld_size.setRange(state._DOME_SCALE_SLIDER_MIN, state._DOME_SCALE_SLIDER_MAX)
        self._sld_size.setValue(state._scale_to_slider_pos(state._DOME_DIAGRAM_SCALE))
        self._lbl_size_val = QLabel(f"{int(state._DOME_DIAGRAM_SCALE * 100)}%")

        size_holder = QWidget()
        size_holder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl_size = QHBoxLayout(size_holder)
        hl_size.setContentsMargins(0, 0, 0, 0)
        hl_size.addWidget(self._sld_size, 1)
        hl_size.addWidget(self._lbl_size_val)
        dl2.addRow(_t("Diagram size") + ":", size_holder)

        self._btn_set_center = QPushButton(_t("Set Center"))
        self._btn_set_center.clicked.connect(self._trigger_set_center_from_dialog)
        self._lbl_center_cap = QLabel(_t("Center:"))
        c0 = get_dome_center()
        self._lbl_center_val = QLabel(f"{c0.x():.2f}, {c0.y():.2f}, {c0.z():.2f}")
        hl_center = QHBoxLayout()
        hl_center.addWidget(self._btn_set_center)
        hl_center.addWidget(self._lbl_center_cap)
        hl_center.addWidget(self._lbl_center_val)
        hl_center.addStretch(1)
        dl2.addRow("", hl_center)

        self._chk_analemas = QCheckBox(_t("Analemas"))
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours = QCheckBox(_t("Hour labels"))
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates = QCheckBox(_t("Date labels"))
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass = QCheckBox(_t("Compass N"))
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        dl2.addRow(self._chk_analemas)
        dl2.addRow(self._chk_hours)
        dl2.addRow(self._chk_dates)
        dl2.addRow(self._chk_compass)
        lay.addWidget(self._dome_box)

        # --- Botões do Domo ---
        self._btn_toggle_shadows_dlg = QPushButton(_t("Shadows on/off"))
        self._btn_toggle_shadows_dlg.setCheckable(True)
        self._btn_toggle_shadows_dlg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if sh is not None:
            self._btn_toggle_shadows_dlg.setChecked(getattr(sh, "enabled", True))
        self._btn_toggle_shadows_dlg.toggled.connect(self._on_toggle_shadows_panel)
        lay.addWidget(self._btn_toggle_shadows_dlg)

        self._btn_toggle_arrow = QPushButton(_t("Sun Arrow"))
        self._btn_toggle_arrow.setCheckable(True)
        self._btn_toggle_arrow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_toggle_arrow.setChecked(state._OVERLAY_VISIBLE)
        self._btn_toggle_arrow.toggled.connect(self._on_toggle_arrow_dialog)
        lay.addWidget(self._btn_toggle_arrow)

        self._btn_toggle_vector = QPushButton(_t("Sun Vector"))
        self._btn_toggle_vector.setCheckable(True)
        self._btn_toggle_vector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_toggle_vector.setChecked(state._SUN_VECTOR_ACTIVE)
        self._btn_toggle_vector.toggled.connect(self._on_toggle_vector_dialog)
        lay.addWidget(self._btn_toggle_vector)

        self._btn_toggle_dome = QPushButton(_t("Sun Dome"))
        self._btn_toggle_dome.setCheckable(True)
        self._btn_toggle_dome.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_toggle_dome.setChecked(state._SUN_DOME_ACTIVE)
        self._btn_toggle_dome.toggled.connect(self._on_toggle_dome_dialog)
        lay.addWidget(self._btn_toggle_dome)

        # --- Playback ---
        gb_rep = QGroupBox(_t("Playback"))
        gb_rep.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        gb_rep.setMinimumWidth(0)
        v_rep = QVBoxLayout(gb_rep)
        self._combo_step = QComboBox()
        self._combo_step.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for m in (60, 30, 15, 10, 5, 1):
            self._combo_step.addItem(_t("{n} min/step").replace("{n}", str(m)), m)
        self._combo_step.setCurrentIndex(1)
        self._combo_step.currentIndexChanged.connect(self._on_step_changed)
        v_rep.addWidget(QLabel(_t("Step per frame:")))
        v_rep.addWidget(self._combo_step)

        self._chk_include_dome = QCheckBox(_t("Include Sun Dome in export"))
        self._chk_include_dome.setChecked(True)
        self._chk_include_dome.stateChanged.connect(self._on_include_dome_changed)
        v_rep.addWidget(self._chk_include_dome)

        h_rep = QHBoxLayout()
        self._btn_play = QPushButton(_t("Play"))
        self._btn_play.setCheckable(True)
        self._btn_play.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_play.clicked.connect(self._on_play)
        h_rep.addWidget(self._btn_play)
        self._btn_stop = QPushButton(_t("Stop"))
        self._btn_stop.setCheckable(True)
        self._btn_stop.setChecked(True)
        self._btn_stop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_stop.clicked.connect(self._on_stop)
        h_rep.addWidget(self._btn_stop)
        v_rep.addLayout(h_rep)
        lay.addWidget(gb_rep)

        # --- Export ---
        gb_exp = QGroupBox(_t("Export"))
        gb_exp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        gb_exp.setMinimumWidth(0)
        v_exp = QVBoxLayout(gb_exp)
        self._combo_format = QComboBox()
        self._combo_format.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo_format.addItems([_t("PNG image sequence"), _t("MP4 video")])
        v_exp.addWidget(QLabel(_t("Output format:")))
        v_exp.addWidget(self._combo_format)

        self._sb_export_w = QSpinBox()
        self._sb_export_w.setRange(16, 7680)
        self._sb_export_w.setValue(1920)
        self._sb_export_w.setSuffix(" px")
        self._sb_export_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._sb_export_h = QSpinBox()
        self._sb_export_h.setRange(16, 7680)
        self._sb_export_h.setValue(1080)
        self._sb_export_h.setSuffix(" px")
        self._sb_export_h.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._chk_lock = QCheckBox(_t("Keep aspect ratio"))
        self._chk_lock.setChecked(True)

        h_size = QHBoxLayout()
        h_size.setSpacing(4)
        h_size.addWidget(QLabel(_t("W")))
        h_size.addWidget(self._sb_export_w, 1)
        h_size.addWidget(QLabel(_t("x  H")))
        h_size.addWidget(self._sb_export_h, 1)
        v_exp.addLayout(h_size)
        v_exp.addWidget(self._chk_lock)

        self._btn_export = QPushButton(_t("Export Animation"))
        self._btn_export.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_export.clicked.connect(self._on_export)
        v_exp.addWidget(self._btn_export)
        lay.addWidget(gb_exp)

        self._chk_lock.toggled.connect(self._update_lock_state)
        self._sb_export_w.valueChanged.connect(self._w_mudou)
        self._sb_export_h.valueChanged.connect(self._h_mudou)
        self._update_lock_state(self._chk_lock.isChecked())

        # --- Dependências ---
        gb_dep = QGroupBox(_t("Video Dependencies"))
        gb_dep.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        gb_dep.setMinimumWidth(0)
        v_dep = QVBoxLayout(gb_dep)
        self._lbl_ffmpeg = QLabel("")
        self._lbl_ffmpeg.setWordWrap(True)
        v_dep.addWidget(self._lbl_ffmpeg)
        self._btn_dep = QPushButton(_t("Configure / Download..."))
        self._btn_dep.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_dep.clicked.connect(self._on_deps)
        v_dep.addWidget(self._btn_dep)
        lay.addWidget(gb_dep)

        lay.addStretch(1)
        scroll.setWidget(container)
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        main_lay.addWidget(scroll, 1)

        self._sld_date.valueChanged.connect(self._on_date)
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

        self._refresh_solar_readout()
        self._refresh_dome_controls_visibility()
        self.sync_dome_checkboxes()
        self._refresh_ffmpeg_status()
        try:
            self._polish_dynamic_widths()
        except Exception:
            traceback.print_exc()

    # --- Métodos ---
    def _on_step_changed(self, idx):
        minutes = self._combo_step.itemData(idx)
        if minutes: self._animator.set_step_minutes(minutes)

    def _on_include_dome_changed(self, state_val):
        if hasattr(self, "_animator"):
            self._animator.set_include_dome(
                state_val == Qt.Checked.value if hasattr(Qt.Checked, "value") else state_val)

    def _on_play(self):
        self._animator.play()
        self._btn_play.setChecked(True)
        self._btn_stop.setChecked(False)

    def _on_stop(self):
        self._animator.stop()
        self._btn_play.setChecked(False)
        self._btn_stop.setChecked(True)

    def _on_export(self):
        modo = "MP4" if self._combo_format.currentIndex() == 1 else "PNG"
        size = (int(self._sb_export_w.value()), int(self._sb_export_h.value()))
        keep_ratio = bool(self._chk_lock.isChecked())
        base_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if not base_dir or not os.path.isdir(base_dir):
            base_dir = os.path.expanduser("~")

        if modo == "PNG":
            out_dir = QFileDialog.getExistingDirectory(
                self._mw, _t("Folder to save PNG frames"), base_dir)
            if not out_dir: return
            self._animator.configure_export(
                output_png_dir=out_dir, size=size,
                keep_aspect_ratio=keep_ratio)
        else:
            out_file, _ = QFileDialog.getSaveFileName(
                self._mw, _t("Save MP4 video"),
                os.path.join(base_dir, "sunpath.mp4"), _t("MP4 video (*.mp4)"))
            if not out_file: return
            if not out_file.lower().endswith(".mp4"): out_file += ".mp4"
            self._animator.configure_export(
                output_mp4=out_file, size=size,
                keep_aspect_ratio=keep_ratio)
        self._animator.play()

    def _update_lock_state(self, checked):
        self._sb_export_h.setEnabled(not checked)
        if checked: self._w_mudou(self._sb_export_w.value())

    def _w_mudou(self, val):
        if self._chk_lock.isChecked():
            vp = getattr(self._mw, "viewport", None)
            aspect = 1.0
            if vp and vp.height() > 0: aspect = vp.width() / vp.height()
            self._sb_export_h.blockSignals(True)
            self._sb_export_h.setValue(max(16, int(round(val / aspect))))
            self._sb_export_h.blockSignals(False)

    def _h_mudou(self, val):
        if self._chk_lock.isChecked():
            vp = getattr(self._mw, "viewport", None)
            aspect = 1.0
            if vp and vp.height() > 0: aspect = vp.width() / vp.height()
            self._sb_export_w.blockSignals(True)
            self._sb_export_w.setValue(max(16, int(round(val * aspect))))
            self._sb_export_w.blockSignals(False)

    def _on_deps(self):
        DependencyDialog(self).exec()
        self._refresh_ffmpeg_status()

    def _refresh_ffmpeg_status(self):
        p = _find_ffmpeg()
        self._lbl_ffmpeg.setText(_t("FFmpeg: Available") if p else _t("FFmpeg: MISSING"))

    def _trigger_set_center_from_dialog(self):
        state._DIALOG_HIDDEN_FOR_PICKING = True
        start_picking_center(self._mw, dialog_to_restore=None)

    def _refresh_dome_controls_visibility(self):
        self._dome_box.setVisible(state._SUN_DOME_ACTIVE)

    def _on_toggle_shadows_panel(self, checked):
        """Aplica o estado de sombras vindo do botão (checked real do Qt)."""
        sh = get_shadows(self._mw)
        if sh is not None:
            sh.enabled = bool(checked)
        dlg = getattr(state, "_DIALOG", None)
        if dlg is not None and hasattr(dlg, "_btn_toggle_shadows_dlg"):
            try:
                dlg._btn_toggle_shadows_dlg.blockSignals(True)
                dlg._btn_toggle_shadows_dlg.setChecked(bool(checked))
                dlg._btn_toggle_shadows_dlg.blockSignals(False)
            except Exception:
                pass
        try:
            from . import toolbar as _tb
            for action, english, _tip in _tb._LABELED_ACTIONS:
                if english == "Shadows on/off":
                    action.blockSignals(True)
                    action.setChecked(bool(checked))
                    action.blockSignals(False)
                    break
        except Exception:
            pass
        repaint(self._mw)

    def _on_toggle_arrow_dialog(self, checked):
        state._OVERLAY_VISIBLE = checked
        set_overlay_visible(self._mw, checked)
        save_state_to_scene(self._mw)

    def _on_toggle_vector_dialog(self, checked):
        state._SUN_VECTOR_ACTIVE = checked
        sync_overlay_visibility(self._mw)
        save_state_to_scene(self._mw)
        repaint(self._mw)

    def _on_toggle_dome_dialog(self, checked):
        state._SUN_DOME_ACTIVE = checked
        state._HOVER_CELL_IDX = -1
        sync_overlay_visibility(self._mw)
        save_state_to_scene(self._mw)
        repaint(self._mw)
        if checked: show_dome_status_message(self._mw)
        self._refresh_dome_controls_visibility()
        self.sync_dome_checkboxes()

    def _on_diagram_size(self, v):
        state._DOME_DIAGRAM_SCALE = state._slider_pos_to_scale(v)
        self._lbl_size_val.setText(f"{int(round(state._DOME_DIAGRAM_SCALE * 100))}%")
        invalidate_dome_cache()
        save_state_to_scene(self._mw)
        repaint(self._mw)

    def _on_toggle_analemas(self, c):
        state._DOME_SHOW_ANALEMAS = c
        invalidate_dome_cache()
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_hours(self, c):
        state._DOME_SHOW_HOUR_LABELS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_dates(self, c):
        state._DOME_SHOW_DATE_LABELS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_toggle_compass(self, c):
        state._DOME_SHOW_COMPASS = c
        save_state_to_scene(self._mw); repaint(self._mw)

    def _on_north_offset_changed(self, v):
        from .georef import push_north_to_native, scene_set_attr
        deg = push_north_to_native(self._mw, float(v))
        state._NORTH_ROTATION_DEG = deg
        # O push_north_to_native já gravou no atributo correto;
        # não reescrever para evitar inconsistência entre georef e north_deg.
        invalidate_dome_cache()
        save_state_to_scene(self._mw)
        repaint(self._mw)
    
    def _on_source_changed(self, idx):
        sid = self._combo_source.itemData(idx)
        if sid: state._SELECTED_MAP_SID = sid

    def _on_coords_edited(self):
        try:
            parts = [float(p.strip()) for p in self._edit_coords.text().split(",")]
            if len(parts) == 2: _change_location(self._mw, parts[0], parts[1])
        except ValueError: pass

    def _on_open_location_picker(self):
        coords = _open_native_georef_dialog(self._mw)
        if coords is not None:
            lat, lon = coords
            self._edit_coords.setText(f"{lat:.6f}, {lon:.6f}")
            _change_location(self._mw, lat, lon)

    def _on_load_map_changed(self, state_val):
        try: state._LOAD_MAP_TOO = (int(state_val) == int(Qt.Checked))
        except Exception: state._LOAD_MAP_TOO = bool(state_val)

    def _date_text(self, doy):
        d = QDate(2026, 1, 1).addDays(doy - 1)
        from .i18n_loader import _months
        return f"{d.day():02d} {_months()[d.month() - 1]}"

    def _time_text(self, mn): return f"{mn // 60:02d}:{mn % 60:02d}"

    def _refresh_solar_readout(self):
        sh = get_shadows(self._mw)
        lat, _ = get_georef(self._mw)
        az, el = solar_position(sh, lat)
        self._lbl_az_val.setText(f"{az:.1f}°")
        self._lbl_el_val.setText(f"{el:.1f}°")
        if sh is not None:
            from .solar_math import get_sunrise_sunset_hours
            horas = get_sunrise_sunset_hours(sh.month, sh.day, lat)
            if horas:
                h_sr, m_sr, h_ss, m_ss = horas
                self._lbl_sunrise.setText(_t("Sunrise: {h:02d}:{m:02d}").format(h=h_sr, m=m_sr))
                self._lbl_sunset.setText(_t("Sunset: {h:02d}:{m:02d}").format(h=h_ss, m=m_ss))
            else:
                self._lbl_sunrise.setText(_t("Sunrise: --:--"))
                self._lbl_sunset.setText(_t("Sunset: --:--"))

    def _on_date(self, doy):
        self._lbl_date.setText(self._date_text(doy))
        sh = get_shadows(self._mw)
        if sh:
            m, d = day_of_year_to_date(doy)
            set_date(sh, m, d)
            repaint(self._mw)
            self._refresh_solar_readout()

    def _on_time(self, mn):
        self._lbl_time.setText(self._time_text(mn))
        sh = get_shadows(self._mw)
        if sh:
            set_time(sh, mn // 60, mn % 60)
            repaint(self._mw)
            self._refresh_solar_readout()

    def sync_dome_checkboxes(self):
        self._chk_analemas.blockSignals(True)
        self._chk_hours.blockSignals(True)
        self._chk_dates.blockSignals(True)
        self._chk_compass.blockSignals(True)
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        self._chk_analemas.blockSignals(False)
        self._chk_hours.blockSignals(False)
        self._chk_dates.blockSignals(False)
        self._chk_compass.blockSignals(False)

    def _polish_dynamic_widths(self):
        """Garante que sliders/combos/edits acompanhem a largura do dock."""
        from PySide6.QtWidgets import (
            QWidget, QSlider, QComboBox, QLineEdit, QAbstractSpinBox,
            QGroupBox, QSizePolicy, QLabel, QPushButton,
            QCheckBox, QScrollArea, QHBoxLayout,
        )

        def _of_types(types):
            # ``findChildren`` só aceita um tipo; filtre por ``isinstance``
            # para funcionar em todas as versões do PySide6.
            return [w for w in self.findChildren(QWidget)
                    if isinstance(w, types)]

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for sa in self.findChildren(QScrollArea):
            sa.setWidgetResizable(True)
            sa.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            inner = sa.widget()
            if inner is not None:
                inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                inner.setMinimumWidth(0)

        for w in _of_types((QSlider, QComboBox, QLineEdit,
                            QAbstractSpinBox, QGroupBox)):
            sp = w.sizePolicy()
            sp.setHorizontalPolicy(QSizePolicy.Expanding)
            if isinstance(w, QGroupBox):
                sp.setVerticalPolicy(QSizePolicy.Preferred)
            else:
                sp.setVerticalPolicy(QSizePolicy.Fixed)
            w.setSizePolicy(sp)
            w.setMinimumWidth(0)
            if w.maximumWidth() < 200:
                w.setMaximumWidth(16777215)

        for w in _of_types((QPushButton, QCheckBox)):
            sp = w.sizePolicy()
            sp.setHorizontalPolicy(QSizePolicy.Preferred)
            w.setSizePolicy(sp)
            w.setMinimumWidth(0)

        for w in _of_types(QLabel):
            sp = w.sizePolicy()
            sp.setHorizontalPolicy(QSizePolicy.Preferred)
            w.setSizePolicy(sp)
            w.setMinimumWidth(0)

        for lay in self.findChildren(QHBoxLayout):
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, QSlider) and lay.stretch(i) == 0:
                    lay.setStretch(i, 1)

    def sync_ui_from_state(self):
        """Atualiza os controles visuais com o estado global."""
        self._sld_size.blockSignals(True)
        self._sld_size.setValue(state._scale_to_slider_pos(state._DOME_DIAGRAM_SCALE))
        self._sld_size.blockSignals(False)
        self._lbl_size_val.setText(f"{int(round(state._DOME_DIAGRAM_SCALE * 100))}%")

        self._spin_north_cfg.blockSignals(True)
        self._spin_north_cfg.setValue(state._NORTH_ROTATION_DEG)
        self._spin_north_cfg.blockSignals(False)

        self._chk_analemas.blockSignals(True)
        self._chk_hours.blockSignals(True)
        self._chk_dates.blockSignals(True)
        self._chk_compass.blockSignals(True)
        self._chk_analemas.setChecked(state._DOME_SHOW_ANALEMAS)
        self._chk_hours.setChecked(state._DOME_SHOW_HOUR_LABELS)
        self._chk_dates.setChecked(state._DOME_SHOW_DATE_LABELS)
        self._chk_compass.setChecked(state._DOME_SHOW_COMPASS)
        self._chk_analemas.blockSignals(False)
        self._chk_hours.blockSignals(False)
        self._chk_dates.blockSignals(False)
        self._chk_compass.blockSignals(False)

        self._btn_toggle_arrow.blockSignals(True)
        self._btn_toggle_vector.blockSignals(True)
        self._btn_toggle_dome.blockSignals(True)
        self._btn_toggle_arrow.setChecked(state._OVERLAY_VISIBLE)
        self._btn_toggle_vector.setChecked(state._SUN_VECTOR_ACTIVE)
        self._btn_toggle_dome.setChecked(state._SUN_DOME_ACTIVE)
        self._btn_toggle_arrow.blockSignals(False)
        self._btn_toggle_vector.blockSignals(False)
        self._btn_toggle_dome.blockSignals(False)

        from .dome_geometry import get_dome_center
        c = get_dome_center()
        self._lbl_center_val.setText(f"{c.x():.2f}, {c.y():.2f}, {c.z():.2f}")

        self._refresh_dome_controls_visibility()


# =========================================================================
# Helper local (evita import circular com toolbar.py)
# =========================================================================
def _trigger_native_or_toggle_shadows(main_window) -> None:
    """Alterna sombras sem depender do toolbar (evita import circular)."""
    sh = get_shadows(main_window)
    new_state = True
    if sh is not None:
        sh.enabled = not getattr(sh, "enabled", True)
        new_state = sh.enabled

    menubar = getattr(main_window, "menuBar", None)
    if callable(menubar):
        bar = menubar()
        if bar is not None:
            for a in bar.findChildren(QAction):
                txt = a.text()
                if any(k in txt.lower() for k in ("shadow", "sombra")):
                    a.trigger()
                    break
    repaint(main_window)