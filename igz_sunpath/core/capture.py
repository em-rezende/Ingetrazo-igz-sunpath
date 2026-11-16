# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: capture.py
# Descrição: Exportação de PNG do viewport + overlay.
# =========================================================================
import os
import tempfile
import traceback

from PySide6.QtCore import Qt, QPoint, QStandardPaths, QDateTime
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QVBoxLayout, QLabel, QCheckBox,
    QDialogButtonBox, QFileDialog,
)

from . import state
from .i18n_loader import _t
from .georef import get_viewport, get_scene
from .scene_state import save_state_to_scene


def _discover_main_window():
    try:
        qapp = QApplication.instance()
        if qapp is None:
            return None
        for w in qapp.topLevelWidgets():
            if type(w).__name__ == "MainWindow":
                return w
        for w in qapp.topLevelWidgets():
            if hasattr(w, "addToolBar"):
                return w
    except Exception:
        traceback.print_exc()
    return None


class _ExportPngDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Save PNG"))
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self._transparent = bool(state._EXPORT_TRANSPARENT_BG)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl_title = QLabel(_t("Export options"))
        f = lbl_title.font()
        f.setBold(True)
        lbl_title.setFont(f)
        lay.addWidget(lbl_title)

        self._chk_transparent = QCheckBox(_t("Transparent background"))
        self._chk_transparent.setChecked(self._transparent)
        self._chk_transparent.setToolTip(
            _t("If checked, the exported PNG will have a transparent background."))
        lay.addWidget(self._chk_transparent)

        self._lbl_hint = QLabel(_t(
            "The image will include the viewport and the solar overlay."))
        self._lbl_hint.setWordWrap(True)
        # self._lbl_hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self._lbl_hint)

        bb = QDialogButtonBox(self)
        bb.addButton(_t("Continue"), QDialogButtonBox.AcceptRole)
        bb.addButton(_t("Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_accept(self):
        state._EXPORT_TRANSPARENT_BG = bool(self._chk_transparent.isChecked())
        try:
            mw = _discover_main_window()
            if mw is not None:
                save_state_to_scene(mw)
        except Exception:
            traceback.print_exc()
        self.accept()

    def is_transparent(self) -> bool:
        return bool(self._chk_transparent.isChecked())


def _capture_viewport_to_png(main_window, file_path: str) -> bool:
    if main_window is None:
        main_window = _discover_main_window()
    vp = get_viewport(main_window)
    if vp is None:
        return False

    w = int(vp.width())
    h = int(vp.height())
    if w <= 0 or h <= 0:
        return False

    if state._EXPORT_TRANSPARENT_BG:
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        ov = state._OVERLAY
        if ov is not None and ov.isVisible():
            p = QPainter(img)
            try:
                ov.render(p, QPoint(0, 0))
            finally:
                p.end()
    else:
        pix = QPixmap(w, h)
        pix.fill(Qt.white)
        ov = state._OVERLAY
        ov_was_visible = ov is not None and ov.isVisible()
        if ov_was_visible:
            ov.setVisible(False)
        try:
            vp.render(pix)
        finally:
            if ov_was_visible:
                ov.setVisible(True)
        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        if img.isNull():
            return False
        if ov is not None and ov.isVisible():
            p = QPainter(img)
            try:
                ov.render(p, QPoint(0, 0))
            finally:
                p.end()

    if img.isNull() or img.width() <= 0 or img.height() <= 0:
        return False

    path_norm = os.path.normpath(file_path).strip()
    return img.save(path_norm, "PNG")


def export_screenshot(main_window) -> None:
    if main_window is None:
        main_window = _discover_main_window()
    if main_window is None:
        QMessageBox.warning(None, _t("Save PNG"),
                            _t("Could not locate the IngeTrazo main window."))
        return

    try:
        dlg = _ExportPngDialog(parent=main_window)
        if dlg.exec() != QDialog.Accepted:
            return
    except Exception:
        traceback.print_exc()
        return

    try:
        default_dir = QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation) or state.get_here()
        stamp = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        default_name = os.path.join(default_dir, f"sunpath_{stamp}.png")
        path, _flt = QFileDialog.getSaveFileName(
            main_window, _t("Save PNG"), default_name,
            "PNG (*.png);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
    except Exception:
        traceback.print_exc()
        return

    ok = _capture_viewport_to_png(main_window, path)

    final_path = path
    fallback_used = False
    if not ok:
        try:
            fallback_dir = os.path.join(tempfile.gettempdir(), "igz_sunpath")
            os.makedirs(fallback_dir, exist_ok=True)
            fallback_path = os.path.join(
                fallback_dir, os.path.basename(os.path.normpath(path)))
            ok = _capture_viewport_to_png(main_window, fallback_path)
            if ok:
                final_path = fallback_path
                fallback_used = True
        except Exception:
            traceback.print_exc()

    if not ok:
        QMessageBox.warning(
            main_window, _t("Save PNG"),
            _t("Could not save the image to:\n{path}").format(path=path))
        return

    try:
        sb = main_window.statusBar() if hasattr(main_window, "statusBar") else None
        if sb is not None:
            msg = _t("Image saved: {path}").format(path=final_path)
            sb.showMessage(msg, 6000)
    except Exception:
        pass