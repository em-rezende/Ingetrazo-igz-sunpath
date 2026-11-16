# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: toolbar.py
# Descrição: Criação da toolbar, menu e painel via app.add_panel.
# =========================================================================
import os
import traceback

from PySide6.QtCore import Qt, QTimer, QDate, QTime, QSize
from PySide6.QtWidgets import (
    QToolBar, QSizePolicy, QMessageBox, QApplication, QWidget, QTabBar
)
from PySide6.QtGui import QAction

from . import state
from .i18n_loader import _t
from .georef import get_scene, get_viewport, get_georef, read_north_rotation
from .shadows import get_shadows, set_date, set_time
from .solar_math import solar_position
from .dome_geometry import invalidate_dome_cache
from .scene_state import (
    load_state_from_scene, repaint, save_state_to_scene,
)
from .overlay import (
    load_themed_icon, sync_overlay_visibility, show_dome_status_message,
    ensure_overlay, set_overlay_visible, discover_main_window,
    start_picking_center,
)

from .panel import SetSunDialog, SunPathPanel, ShadowsCalendarDialog


_LABELED_ACTIONS = []
_REFRESH_HOOKS = []

_PANEL_DOCK = None
_PANEL_TOGGLE = None
_TOOLBAR_CREATED = False


# --- 3 estados (idênticos ao meu_plugin) --------------------------------
def _bring_dock_to_front(window, dock):
    if dock is None:
        return
    try:
        siblings = dock.tabifiedDockWidgets()
    except Exception:
        siblings = []
    try:
        for sib in siblings:
            sib.lower()
    except Exception:
        pass
    try:
        dock.setVisible(True)
    except Exception:
        pass
    try:
        dock.raise_()
    except Exception:
        pass
    if siblings:
        try:
            title = dock.windowTitle()
            for tb in window.findChildren(QTabBar):
                for i in range(tb.count()):
                    if tb.tabText(i) == title:
                        tb.setCurrentIndex(i)
                        return
        except Exception:
            pass


def _dock_is_front(dock):
    if dock is None:
        return False
    try:
        if not dock.isVisible():
            return False
    except Exception:
        return False
    try:
        siblings = dock.tabifiedDockWidgets()
    except Exception:
        siblings = []
    return not bool(siblings)


# --- Helpers: set center / calendar / shadows --------------------------
def _trigger_native_or_toggle_shadows(main_window) -> None:
    sh = get_shadows(main_window)
    new_state = True
    if sh is not None:
        sh.enabled = not getattr(sh, "enabled", True)
        new_state = sh.enabled
    for action, english, _tt in _LABELED_ACTIONS:
        if english == "Shadows on/off":
            action.blockSignals(True)
            action.setChecked(new_state)
            action.blockSignals(False)
            break
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


def _trigger_calendar(main_window) -> None:
    sh = get_shadows(main_window)
    init_d = QDate(2026, sh.month, sh.day) if sh else QDate.currentDate()
    init_t = QTime(sh.hour, sh.minute) if sh else QTime(12, 0)
    dlg = ShadowsCalendarDialog(parent=main_window,
                                initial_date=init_d, initial_time=init_t)
    if dlg.exec() == __import__("PySide6.QtWidgets", fromlist=["QDialog"]).QDialog.Accepted:
        sd, st = dlg.get_date_time()
        if sh is not None:
            set_date(sh, sd.month(), sd.day())
            set_time(sh, st.hour(), st.minute())
        invalidate_dome_cache()
        if state._DIALOG is not None:
            try:
                if hasattr(state._DIALOG, "_sld_date"):
                    state._DIALOG._sld_date.setValue(sd.dayOfYear())
                if hasattr(state._DIALOG, "_sld_time"):
                    state._DIALOG._sld_time.setValue(st.hour() * 60 + st.minute())
                if hasattr(state._DIALOG, "_refresh_solar_readout"):
                    state._DIALOG._refresh_solar_readout()
            except Exception:
                pass
        repaint(main_window)


# --- Watchers ----------------------------------------------------------
_LAST_SCENE_ID = None
_LAST_HAS_GEO = None
_LAST_NORTH = None
_LAST_LATLON = None
_LAST_DOME_DATE = None


def _poll_scene_change() -> None:
    global _LAST_SCENE_ID, _LAST_HAS_GEO, _LAST_NORTH, _LAST_LATLON
    global _LAST_DOME_DATE
    mw = discover_main_window()
    if mw is None:
        return
    sc = get_scene(mw)
    sid = id(sc) if sc is not None else None
    gr = getattr(sc, "georef", None) if sc is not None else None
    has_geo = gr is not None
    if _LAST_SCENE_ID is None:
        _LAST_SCENE_ID = sid
        _LAST_HAS_GEO = has_geo
        _LAST_LATLON = get_georef(mw)
        load_state_from_scene(mw)                 # linha de read_north_rotation REMOVIDA
        _LAST_NORTH = state._NORTH_ROTATION_DEG
        sync_overlay_visibility(mw)
        return
    if sid != _LAST_SCENE_ID:
        _LAST_SCENE_ID = sid
        _LAST_HAS_GEO = has_geo
        invalidate_dome_cache()
        state._HOVER_CELL_IDX = -1
        # Documento novo/aberto: o document_data dele é a verdade.
        # Pequeno atraso para o IngeTrazo terminar de popular o documento.
        QTimer.singleShot(300, lambda: _reload_for_new_document(mw))
        sync_overlay_visibility(mw)
    if has_geo != _LAST_HAS_GEO:
        _LAST_HAS_GEO = has_geo
        invalidate_dome_cache()
    ll = get_georef(mw)
    if ll != _LAST_LATLON:
        _LAST_LATLON = ll
        invalidate_dome_cache()
    sh = get_shadows(mw)
    if sh is not None:
        cd = (int(sh.month), int(sh.day))
        if cd != _LAST_DOME_DATE:
            _LAST_DOME_DATE = cd
            invalidate_dome_cache()

    n = read_north_rotation(sc) if has_geo else None
    if n is not None and _LAST_NORTH is not None and abs(n - _LAST_NORTH) > 1e-6:
        _LAST_NORTH = n                      # a cena mudou durante a sessão
        state._NORTH_ROTATION_DEG = n
        invalidate_dome_cache()
        save_state_to_scene(mw)
    
    if state._DIALOG is not None and hasattr(state._DIALOG, "_spin_north_cfg"):
        try:
            cur = float(state._NORTH_ROTATION_DEG) % 360.0
            spin = state._DIALOG._spin_north_cfg
            if abs(spin.value() - cur) > 1e-3:
                spin.blockSignals(True)
                spin.setValue(cur)
                spin.blockSignals(False)
        except Exception:
            pass
    if state._OVERLAY is not None and state._OVERLAY.isVisible():
        state._OVERLAY.update()


# --- Toggle season -----------------------------------------------------
def _toggle_season_groups(main_window):
    if not state._SUN_DOME_ACTIVE:
        return
    from PySide6.QtWidgets import QLineEdit, QDoubleSpinBox, QSlider, QComboBox
    focus_w = QApplication.focusWidget()
    if isinstance(focus_w, (QLineEdit, QDoubleSpinBox, QSlider, QComboBox)):
        return
    state._USE_SECOND_HALF_YEAR = not state._USE_SECOND_HALF_YEAR
    state._HOVER_CELL_IDX = -1
    invalidate_dome_cache()
    if state._OVERLAY is not None:
        state._OVERLAY.update()
    mw = main_window if main_window is not None else discover_main_window()
    show_dome_status_message(mw)


# --- Ação "Set Sun" ----------------------------------------------------
def _open_set_sun(main_window):
    from .panel import SetSunDialog
    from PySide6.QtCore import QTimer
    import traceback

    if getattr(state, "_DIALOG", None) is not None:
        try:
            state._DIALOG.show()
            state._DIALOG.raise_()
            state._DIALOG.activateWindow()
            return
        except RuntimeError:
            state._DIALOG = None
        except Exception:
            state._DIALOG = None

    try:
        dlg = SetSunDialog(main_window, parent=None)
        dlg.setWindowFlags(
            Qt.Window 
            | Qt.WindowCloseButtonHint 
            | Qt.WindowTitleHint
            | Qt.WindowMinimizeButtonHint
        )

        # --- Timer que verifica se a janela principal ainda está viva ---
        # Se o IngeTrazo for fechado (mesmo abruptamente), o timer detecta
        # que a main_window não existe mais e fecha o diálogo.
        _check_timer = QTimer(dlg)
        _check_timer.setInterval(500)  # a cada 500ms

        def _check_parent_alive():
            try:
                if main_window is None or not main_window.isVisible():
                    dlg.close()
                    _check_timer.stop()
            except RuntimeError:
                # A main_window foi destruída pelo Qt
                dlg.close()
                _check_timer.stop()
            except Exception:
                # Qualquer outro erro, fecha por segurança
                dlg.close()
                _check_timer.stop()

        _check_timer.timeout.connect(_check_parent_alive)
        _check_timer.start()
        # Guarda referência no diálogo para não ser coletado
        dlg._check_timer = _check_timer

        # As conexões abaixo são reforços (funcionam se o sinal for emitido)
        qapp = QApplication.instance()
        if qapp is not None:
            try:
                qapp.aboutToQuit.connect(dlg.close)
            except Exception:
                pass
        try:
            main_window.destroyed.connect(dlg.close)
        except Exception:
            pass

        state._DIALOG = dlg 
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()        
        
    except Exception as e:
        print(f"[igz_sunpath] Erro ao abrir SetSunDialog: {e}")
        traceback.print_exc()

# --- Ação "Set Center" (Definir Centro do Domo) -----------------------
def _open_set_center(main_window):
    """Entra no modo de picking para definir a origem 3D do domo.
    Mesmo comportamento do botão 'Definir Centro' do diálogo Ajustar Sol.
    """
    from .panel import SetSunDialog  # evitar import circular em runtime
    from PySide6.QtCore import QTimer

    # Se o diálogo Ajustar Sol estiver aberto, esconde-o durante o picking
    # e restaura ao final (mesmo fluxo do botão interno do diálogo).
    dlg = getattr(state, "_DIALOG", None)
    if dlg is not None:
        try:
            dlg.hide()
        except Exception:
            traceback.print_exc()

    start_picking_center(main_window, dialog_to_restore=dlg)

# --- Attach panel (app.add_panel) --------------------------------------
def attach_panel(app, main_window, panel):
    global _PANEL_DOCK, _PANEL_TOGGLE
    add_panel = getattr(app, "add_panel", None)
    if callable(add_panel):
        try:
            dock = add_panel(_t("Set Sun"), panel,
                             name="igz_sunpath_set_sun", stretch=1)
            _PANEL_DOCK = dock
            try:
                set_icon = getattr(app, "_set_panel_icon", None)
                icon = load_themed_icon("sunpath_panel_tab", main_window)
                if callable(set_icon) and not icon.isNull():
                    set_icon(dock, icon)
            except Exception:
                pass
            try:
                dock.hide()
            except Exception:
                pass
            if hasattr(dock, "toggleViewAction"):
                _PANEL_TOGGLE = dock.toggleViewAction()
            return dock
        except Exception:
            traceback.print_exc()
    return None

# --- Exportar Sequência / Vídeo (menu + toolbar) -----------------------
def _open_export_dialog(main_window):
    """Abre o novo diálogo de exportação (PNG sequence ou MP4)."""
    from .export_dialog import ExportDialog
    from .sun_animator import SunAnimator
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QApplication
    from PySide6.QtCore import QStandardPaths
    import os

    # 1) ExportDialog
    try:
        dlg = ExportDialog(None, main_window, modo_inicial="MP4")
        res = dlg.exec()
        print(f"[igz_sunpath] ExportDialog.exec() -> {res} "
              f"(Accepted={QDialog.Accepted})")
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(main_window, "igz_sunpath",
                             f"Falha ao abrir ExportDialog:\n{e}")
        return

    if res != QDialog.Accepted:
        print("[igz_sunpath] ExportDialog rejeitado — abortando")
        return

    # 2) Lê opções — tenta nomes alternativos para "passo por quadro"
    try:
        modo = dlg.modo_saida()
        size = dlg.tamanho()

        step_min = None
        for name in ("step_minutes", "passo_minutos", "step",
                     "minutes_per_step", "min_per_step",
                     "passo_por_quadro"):
            fn = getattr(dlg, name, None)
            if callable(fn):
                step_min = fn()
                break
        if step_min is None:
            # último recurso: lê direto do combo, se existir
            combo = getattr(dlg, "_combo_step", None) \
                 or getattr(dlg, "combo_step", None)
            if combo is not None:
                step_min = combo.currentData()
        if step_min is None:
            raise AttributeError(
                "ExportDialog não expõe passo por quadro "
                "(esperado: step_minutes/passo_minutos/step)")
        step_min = int(step_min)
        
        # --- lê "keep aspect ratio" (vários nomes possíveis) ---
        keep_ratio = True
        keep_names = ("keep_aspect_ratio", "manter_proporcao",
                      "keep_ratio", "manter_proporcao_tela")
        found_fn = False
        for name in keep_names:
            fn = getattr(dlg, name, None)
            if callable(fn):
                found_fn = True
                try:
                    keep_ratio = bool(fn())
                except Exception:
                    pass
                break
        if not found_fn:
            # fallback: lê direto do checkbox, se existir
            chk = (getattr(dlg, "_chk_keep_ratio", None)
                   or getattr(dlg, "_chk_aspect", None)
                   or getattr(dlg, "chk_keep_ratio", None))
            if chk is not None and hasattr(chk, "isChecked"):
                keep_ratio = bool(chk.isChecked())

        print(f"[igz_sunpath] Export opts: modo={modo!r} "
              f"size={size!r} step={step_min} min/quadro "
              f"keep_ratio={keep_ratio}")
        
        print(f"[igz_sunpath] Export opts: modo={modo!r} "
              f"size={size!r} step={step_min} min/quadro")
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(main_window, "igz_sunpath",
                             f"Erro ao ler opções do ExportDialog:\n{e}")
        return

    # Libera o diálogo antes do file dialog nativo (evita conflito modal no Windows)
    try:
        dlg.deleteLater()
        QApplication.processEvents()
    except Exception:
        pass

    # 3) base_dir com fallback triplo
    base_dir = QStandardPaths.writableLocation(
        QStandardPaths.DocumentsLocation)
    if not base_dir or not os.path.isdir(base_dir):
        base_dir = os.path.expanduser("~")
    if not base_dir or not os.path.isdir(base_dir):
        base_dir = os.getcwd()
    print(f"[igz_sunpath] base_dir={base_dir!r}")

    # 4) QFileDialog — antes do animator
    parent = main_window if main_window is not None else None
    if modo == "PNG":
        try:
            out_path = QFileDialog.getExistingDirectory(
                parent, _t("Folder to save PNG frames"), base_dir,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(main_window, "igz_sunpath",
                                 f"Falha ao abrir seletor de pasta:\n{e}")
            return
        print(f"[igz_sunpath] PNG dir escolhido: {out_path!r}")
        if not out_path:
            return
        kwargs = {"output_png_dir": out_path}
    else:
        try:
            out_path, _ = QFileDialog.getSaveFileName(
                parent, _t("Save MP4 video"),
                os.path.join(base_dir, "sunpath.mp4"),
                _t("MP4 video (*.mp4)"))
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(main_window, "igz_sunpath",
                                 f"Falha ao abrir seletor de arquivo:\n{e}")
            return
        print(f"[igz_sunpath] MP4 path escolhido: {out_path!r}")
        if not out_path:
            return
        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
        kwargs = {"output_mp4": out_path}

    # 5) Resolve animator (painel > SetSunDialog > temporário)
    animator = None
    if _PANEL_DOCK is not None:
        w = _PANEL_DOCK.widget()
        if w is not None and hasattr(w, "_animator"):
            animator = w._animator
    if animator is None and state._DIALOG is not None \
            and hasattr(state._DIALOG, "_animator"):
        animator = state._DIALOG._animator
    if animator is None:
        try:
            animator = SunAnimator(main_window)
            main_window._igz_sunpath_temp_animator = animator
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(main_window, "igz_sunpath",
                                 f"Falha ao criar animator:\n{e}")
            return

    # 6) Dispara — passo por quadro + tamanho
    try:
        if hasattr(animator, "set_step_minutes"):
            animator.set_step_minutes(step_min)
        animator.configure_export(size=size, keep_aspect_ratio=keep_ratio, **kwargs)
        animator.play()
        print("[igz_sunpath] export disparado")
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(main_window, "igz_sunpath",
                             f"Falha ao iniciar exportação:\n{e}")
                             
# --- Toolbar -----------------------------------------------------------
def create_toolbar(main_window, app):
    tb = QToolBar("Sun Path", main_window)
    tb.setObjectName("igz_sunpath_toolbar")
    tb.setWindowTitle(_t("Sun Path"))
    
    try:
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setIconSize(QSize(24, 24))
    except Exception:
        pass

    def make_action(nome_en, icone, tip_en, callback, checkable=False):
        icon = load_themed_icon(icone, main_window)
        action = QAction(icon, _t(nome_en), main_window)
        action.setToolTip(_t(tip_en))
        action.setStatusTip(_t(tip_en))
        action.setCheckable(checkable)
        # Passa o "checked" real do QAction para o callback (quando checkable).
        action.triggered.connect(lambda checked=False: callback(checked))
        _LABELED_ACTIONS.append((action, nome_en, tip_en))
        return action

    # 1. Ajustar Sol (Diálogo)
    def _open_dialog_safe(*_args, **_kwargs):
        try:
            _open_set_sun(main_window)
        except Exception as e:
            print(f"[igz_sunpath] Erro ao abrir o diálogo: {e}")

    tb.addAction(make_action(
        "Set Sun", "sunpath_set_sun", 
        "Open the Sun adjustment window.", 
        _open_dialog_safe
    ))

    tb.addSeparator()

    # 2. Calendário
    tb.addAction(make_action(
        "Calendar", "sunpath_calendar",
         "Open the shadows calendar.",
        lambda *_a, **_k: _trigger_calendar(main_window)
    ))

    # 3. Sombras
    def _toggle_shadows_cb(*_args, **_kwargs):
        _trigger_native_or_toggle_shadows(main_window)
    act_shadow = make_action(
        "Shadows on/off", "sunpath_shadows",
        "Toggle scene shadows.",
        _toggle_shadows_cb, checkable=True)
    sh = get_shadows(main_window)
    if sh is not None:
        act_shadow.setChecked(getattr(sh, "enabled", True))
    tb.addAction(act_shadow)

    # 4. Seta do Sol
    def _toggle_arrow_cb(checked=False):
        state._OVERLAY_VISIBLE = bool(checked)
        set_overlay_visible(main_window, state._OVERLAY_VISIBLE)
        save_state_to_scene(main_window)
        repaint(main_window)
    act_arrow = make_action(
        "Sun Arrow", "sunpath_arrow",
         "Toggle the sun compass overlay.",
        _toggle_arrow_cb, checkable=True)
    act_arrow.setChecked(state._OVERLAY_VISIBLE)
    tb.addAction(act_arrow)

    # 5. Vetor do Sol
    def _toggle_vector_cb(checked=False):
        state._SUN_VECTOR_ACTIVE = bool(checked)
        sync_overlay_visibility(main_window)
        save_state_to_scene(main_window)
        repaint(main_window)
    act_vec = make_action(
        "Sun Vector", "sunpath_vector",
        "Toggle the 3D sun vector.",
        _toggle_vector_cb, checkable=True)
    act_vec.setChecked(state._SUN_VECTOR_ACTIVE)
    tb.addAction(act_vec)

    # 6. Domo do Sol
    def _toggle_dome_cb(checked=False):
        state._SUN_DOME_ACTIVE = bool(checked)
        state._HOVER_CELL_IDX = -1
        sync_overlay_visibility(main_window)
        save_state_to_scene(main_window)
        repaint(main_window)
        if state._SUN_DOME_ACTIVE:
            show_dome_status_message(main_window)
    act_dome = make_action(
        "Sun Dome", "sunpath_dome",
        "Toggle the sun path dome.",
        _toggle_dome_cb, checkable=True)
    act_dome = make_action(
        "Sun Dome", "sunpath_dome",
        "Liga/desliga o domo solar.",
        _toggle_dome_cb, checkable=True)
    act_dome.setChecked(state._SUN_DOME_ACTIVE)
    tb.addAction(act_dome)

    # 6b. Set Center (Definir Centro do Domo) — igual ao original
    tb.addAction(make_action(
        "Set Center", "sunpath_center",
        "Define a origem 3D do domo clicando na viewport (usa OSNAP).",
        lambda *_a, **_k: _open_set_center(main_window)
    ))

    tb.addSeparator()

    # 7. Play do Sol
    def _on_play_toolbar(*_args, **_kwargs):
        if _PANEL_DOCK is not None:
            w = _PANEL_DOCK.widget()
            if hasattr(w, "_animator"):
                w._animator.play()
        elif state._DIALOG is not None:
            if hasattr(state._DIALOG, "_animator"):
                state._DIALOG._animator.play()

    tb.addAction(make_action(
        "Play", "sunpath_play",
        "Start the sun animation.",
        _on_play_toolbar
    ))

    # 8. Stop do Sol
    def _on_stop_toolbar(*_args, **_kwargs):
        if _PANEL_DOCK is not None:
            w = _PANEL_DOCK.widget()
            if hasattr(w, "_animator"):
                w._animator.stop()
        elif state._DIALOG is not None:
            if hasattr(state._DIALOG, "_animator"):
                state._DIALOG._animator.stop()

    tb.addAction(make_action(
        "Stop", "sunpath_stop",
        "Stop the sun animation.",
        _on_stop_toolbar
    ))

    tb.addSeparator()

    # =========================================================================
    # BOTÃO 7: Exportar Sequência de imagens/vídeo
    # =========================================================================

    tb.addAction(make_action(
        "Export Sequence / Video", "sunpath_save",
        "Export the animation as a PNG image sequence or MP4 video.",
        lambda *_a, **_k: _open_export_dialog(main_window)
    ))

    tb.addSeparator()

    # 10. Painel do Sol (Último)
    if _PANEL_DOCK is not None:
        icon_panel = load_themed_icon("sunpath_panel", main_window)
        if icon_panel.isNull():
            icon_panel = load_themed_icon("sunpath_center", main_window)
            
        action_panel = QAction(icon_panel, _t("Sun Panel"), main_window)
        action_panel.setToolTip(_t("Show/hide the Sun side panel."))
        action_panel.setCheckable(True)
        
        try:
            action_panel.setChecked(_PANEL_DOCK.isVisible())
        except Exception:
            action_panel.setChecked(False)

        def _toggle_or_show_panel(_checked=False):
            try:
                d = _PANEL_DOCK
                if d is None:
                    return
                if _dock_is_front(d):
                    d.hide()
                    return
                _bring_dock_to_front(main_window, d)
                try:
                    w = d.widget()
                    if w is not None:
                        w.setFocus()
                except Exception:
                    pass
                try:
                    main_window.raise_()
                    main_window.activateWindow()
                except Exception:
                    pass
            except Exception as exc:
                print(f"[igz_sunpath] toggle painel falhou: {exc}")

        action_panel.triggered.connect(_toggle_or_show_panel)
        
        try:
            _PANEL_DOCK.visibilityChanged.connect(action_panel.setChecked)
        except Exception:
            pass
        
        tb.addAction(action_panel)

    tb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return tb
    
def _refresh_ui_after_load(main_window):
    invalidate_dome_cache()
    state._HOVER_CELL_IDX = -1
    sync_overlay_visibility(main_window)
    if _PANEL_DOCK is not None:
        w = _PANEL_DOCK.widget()
        if hasattr(w, "sync_ui_from_state"):
            w.sync_ui_from_state()
    if state._DIALOG is not None and hasattr(state._DIALOG, "sync_ui_from_state"):
        state._DIALOG.sync_ui_from_state()
    repaint(main_window)


def _reload_for_new_document(main_window):
    global _LAST_NORTH
    try:
        if load_state_from_scene(main_window):
            _LAST_NORTH = state._NORTH_ROTATION_DEG
            _refresh_ui_after_load(main_window)
        else:
            # Documento sem dados do plugin: grava o estado atual nele.
            save_state_to_scene(main_window)
    except Exception:
        traceback.print_exc()


def _load_state_once(main_window):
    _reload_for_new_document(main_window)
    
# --- Setup -------------------------------------------------------------
def setup(app):
    global _TOOLBAR_CREATED
    if _TOOLBAR_CREATED:
        return
    try:
        mw = None
        qapp = QApplication.instance()
        if qapp is not None:
            for w in qapp.topLevelWidgets():
                if hasattr(w, "addToolBar"):
                    mw = w
                    break
        if mw is None:
            mw = (getattr(app, "main_window", None)
                  or getattr(app, "window", None)
                  or (app if hasattr(app, "addToolBar") else None))
        if mw is None or not hasattr(mw, "addToolBar"):
            return
            
        mw._igz_sunpath_app = app

        panel = SunPathPanel(mw, parent=None)
        attach_panel(app, mw, panel)

        tb = create_toolbar(mw, app=app)
        mw.addToolBar(Qt.TopToolBarArea, tb)
        _TOOLBAR_CREATED = True

        try:
            sub = app.add_menu("Sun Path")
            sub.addAction(_t("Set Sun"), lambda: _open_set_sun(mw))
            sub.addAction(_t("Calendar"), lambda: _trigger_calendar(mw))
            sub.addSeparator()
            sub.addAction(_t("Export Sequence / Video"),
                          lambda: _open_export_dialog(mw))
        except Exception:
            pass

        QTimer.singleShot(0, _poll_scene_change)
        _watcher = QTimer()
        _watcher.setInterval(500)
        _watcher.timeout.connect(_poll_scene_change)
        _watcher.start()
        mw._igz_sunpath_watcher = _watcher
        QTimer.singleShot(1000, lambda: _load_state_once(mw))
    except Exception:
        traceback.print_exc()