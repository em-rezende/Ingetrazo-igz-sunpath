# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: sun_animator.py
# Descrição: Controlador de animação do sol (play/stop + export).
# =========================================================================
import os
import shutil
import subprocess
import tempfile
import traceback

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from . import state
from .i18n_loader import _t
from .georef import get_georef, get_viewport
from .shadows import get_shadows, set_time
from .solar_math import get_sunrise_sunset_hours
from .scene_state import repaint


class SunAnimator(QObject):
    """Controla a animação do sol (avança a hora até o pôr do sol)."""

    def __init__(self, main_window):
        super().__init__()
        self._mw = main_window
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.animating = False
        self.speed = 0.5  # horas por tick (0.5 = 30 min)
        self._frame_count = 0
        self._include_dome = True  # Incluir Domo do Sol na exportação
        
        # Exportação
        self._output_png_dir = None
        self._output_mp4 = None
        self._export_fps = 30.0
        self._export_size = None
        self._export_keep_ratio = True
        self._tmp_dir = None
        self._interrupted = False

    def set_include_dome(self, include: bool):
        self._include_dome = include
        
    # --- Configuração pública ------------------------------------------------
    def set_step_minutes(self, minutes):
        """Define o passo em minutos (60, 30, 15, 10, 5, 1)."""
        self.speed = float(minutes) / 60.0

    def configure_export(self, output_png_dir=None, output_mp4=None,
                         fps=30.0, size=None, keep_aspect_ratio=True):
        self._output_png_dir = output_png_dir
        self._output_mp4 = output_mp4
        self._export_fps = float(fps)
        self._export_size = size
        self._export_keep_ratio = bool(keep_aspect_ratio)

    def clear_export(self):
        self._output_png_dir = None
        self._output_mp4 = None
        self._export_keep_ratio = True
        self._tmp_dir = None
        self._frame_count = 0
        self._interrupted = False

    # --- Controle ------------------------------------------------------------
    def play(self):
        sh = get_shadows(self._mw)
        if sh is None:
            return

        lat, _ = get_georef(self._mw)
        horas = get_sunrise_sunset_hours(sh.month, sh.day, lat)

        if horas:
            h_sr, m_sr, h_ss, m_ss = horas
            current_minutes = sh.hour * 60 + sh.minute
            sunrise_minutes = h_sr * 60 + m_sr
            sunset_minutes = h_ss * 60 + m_ss
            if current_minutes >= sunset_minutes or current_minutes < sunrise_minutes:
                set_time(sh, h_sr, m_sr)

        # Se for exportar para MP4, cria a pasta temporária
        if self._output_mp4:
            self._tmp_dir = tempfile.mkdtemp(prefix="igz_sunpath_frames_")

        self._frame_count = 0
        self._interrupted = False
        self.timer.start()
        self.animating = True
        self._sync_buttons(True)

    def stop(self):
        self.timer.stop()
        self.animating = False
        self._sync_buttons(False)
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._tmp_dir = None
        self._output_png_dir = None
        self._output_mp4 = None

    def _tick(self):
        sh = get_shadows(self._mw)
        if sh is None:
            self.stop()
            return

        lat, _ = get_georef(self._mw)
        horas = get_sunrise_sunset_hours(sh.month, sh.day, lat)

        if not horas:
            self.stop()
            return

        h_sr, m_sr, h_ss, m_ss = horas
        current_minutes = sh.hour * 60 + sh.minute
        current_minutes += self.speed * 60

        # Fim do dia: para ou gera vídeo
        if current_minutes >= h_ss * 60 + m_ss:
            set_time(sh, h_ss, m_ss)
            self._capture_frame()
            repaint(self._mw)
            self._on_finished()
            return

        h = int(current_minutes // 60)
        m = int(current_minutes % 60)
        set_time(sh, h, m)

        repaint(self._mw)
        self._capture_frame()
        self._update_ui()

    def _capture_frame(self):
        """Captura a viewport (e o domo, se escolhido) para PNG."""
        if not (self._output_png_dir or self._tmp_dir):
            return
        vp = get_viewport(self._mw)
        if vp is None:
            return

        try:
            if self._include_dome:
                # Captura com o overlay do Domo
                from PySide6.QtGui import QImage, QPainter, QPixmap
                from PySide6.QtCore import Qt, QPoint
                from . import state

                w, h = vp.width(), vp.height()
                pix = QPixmap(w, h)
                pix.fill(Qt.white)
                vp.render(pix)
                img = pix.toImage().convertToFormat(QImage.Format_ARGB32)

                ov = state._OVERLAY
                if ov is not None and ov.isVisible():
                    p = QPainter(img)
                    try:
                        ov.render(p, QPoint(0, 0))
                    finally:
                        p.end()

                pix = QPixmap.fromImage(img)
            else:
                # Apenas a viewport (sem Domo)
                if not hasattr(vp, "grabFramebuffer"):
                    return
                pix = vp.grabFramebuffer()

            if pix is None:
                return

            if self._export_size:
                try:
                    tw, th = int(self._export_size[0]), int(self._export_size[1])
                    if tw > 0 and th > 0 and (tw != pix.width() or th != pix.height()):
                        if self._export_keep_ratio:
                            pix = self._fit_frame_letterbox(pix, tw, th)
                        else:
                            pix = pix.scaled(tw, th,
                                             Qt.IgnoreAspectRatio,
                                             Qt.SmoothTransformation)
                except Exception:
                    traceback.print_exc()

            self._frame_count += 1

            if self._tmp_dir:
                path = os.path.join(self._tmp_dir, f"f_{self._frame_count:05d}.png")
                pix.save(path, "PNG")
            elif self._output_png_dir:
                path = os.path.join(self._output_png_dir, f"frame_{self._frame_count:04d}.png")
                pix.save(path, "PNG")
        except Exception:
            traceback.print_exc()

    def _fit_frame_letterbox(self, pix, out_w: int, out_h: int):
        """Redimensiona preservando proporção, com barras pretas (letterbox).

        Usa QPixmap como canvas e QPainter para desenhar o frame escalado
        centralizado. QPixmap é mais eficiente que QImage para render de
        overlay já que o _capture_frame trabalha com QPixmap.
        """
        from PySide6.QtGui import QPixmap, QPainter
        from PySide6.QtCore import Qt

        scaled = pix.scaled(out_w, out_h,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        canvas = QPixmap(out_w, out_h)
        canvas.fill(Qt.black)
        p = QPainter(canvas)
        try:
            x = (out_w - scaled.width()) // 2
            y = (out_h - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        finally:
            p.end()
        return canvas

    def _update_ui(self):
        if state._DIALOG is not None and hasattr(state._DIALOG, "_sld_time"):
            sh = get_shadows(self._mw)
            if sh is None:
                return
            mins = sh.hour * 60 + sh.minute
            try:
                state._DIALOG._sld_time.blockSignals(True)
                state._DIALOG._sld_time.setValue(mins)
                state._DIALOG._sld_time.blockSignals(False)
                if hasattr(state._DIALOG, "_refresh_solar_readout"):
                    state._DIALOG._refresh_solar_readout()
            except Exception:
                pass

    def _on_finished(self):
        self.timer.stop()
        self.animating = False
        self._sync_buttons(False)

        if self._output_mp4 and self._tmp_dir:
            ok = self._render_mp4()
            if ok:
                QMessageBox.information(
                    self._mw, _t("Animation"),
                    _t("Animation completed! {n} frames.\nVideo saved at:\n{path}",
                       n=self._frame_count, path=self._output_mp4))
            else:
                QMessageBox.warning(
                    self._mw, _t("Animation"),
                    _t("Animation completed, but the video was NOT generated.\n"
                       "Frames kept at:\n{path}", path=self._tmp_dir or "(none)"))
            return

        if self._output_png_dir:
            QMessageBox.information(
                self._mw, _t("Animation"),
                _t("Animation completed! {n} PNG frames saved in:\n{path}",
                   n=self._frame_count, path=self._output_png_dir))
            return

        QMessageBox.information(
            self._mw, _t("Animation"),
            _t("Animation completed! Total frames: {n}.", n=self._frame_count))

    def _render_mp4(self) -> bool:
        from .ffmpeg import _find_ffmpeg, _fps_str
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            QMessageBox.warning(
                self._mw, _t("Animation"),
                _t("FFmpeg was not found. Frames kept at:\n{path}",
                   path=(self._tmp_dir or "")))
            return False

        if not self._tmp_dir or not os.path.isdir(self._tmp_dir):
            return False

        pngs = sorted(f for f in os.listdir(self._tmp_dir) if f.lower().endswith(".png"))
        if not pngs:
            return False

        pattern = os.path.join(self._tmp_dir, "f_%05d.png")
        cmd = [
            ffmpeg, "-y",
            "-framerate", _fps_str(self._export_fps),
            "-start_number", "1",
            "-i", pattern,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            self._output_mp4,
        ]

        try:
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=600)
        except Exception:
            traceback.print_exc()
            return False

        if proc.returncode != 0 or not os.path.isfile(self._output_mp4):
            return False

        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._tmp_dir = None
        return True

    def _sync_buttons(self, playing):
        for widget in [state._DIALOG]:
            if widget is not None:
                if hasattr(widget, "_btn_play"):
                    widget._btn_play.blockSignals(True)
                    widget._btn_play.setChecked(playing)
                    widget._btn_play.blockSignals(False)
                if hasattr(widget, "_btn_stop"):
                    widget._btn_stop.blockSignals(True)
                    widget._btn_stop.setChecked(not playing)
                    widget._btn_stop.blockSignals(False)