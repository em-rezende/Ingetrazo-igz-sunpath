# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: export_dialog.py
# Descrição: Diálogo de opções de exportação (PNG ou MP4).
# =========================================================================
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QSpinBox,
    QHBoxLayout, QLabel, QWidget, QCheckBox, QPushButton,
)

from .i18n_loader import _t
from .ffmpeg import _find_ffmpeg, DependencyDialog


class ExportDialog(QDialog):
    def __init__(self, controller, parent=None, modo_inicial=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Export Animation"))
        self.controller = controller

        layout = QFormLayout(self)

        self.cb_formato = QComboBox()
        self.cb_formato.addItems([_t("PNG image sequence"), _t("MP4 video")])
        if str(modo_inicial).upper() == "MP4":
            self.cb_formato.setCurrentIndex(1)
        layout.addRow(_t("Output format:"), self.cb_formato)

        # --- Passo por quadro ---
        self.cb_step = QComboBox()
        for m in (60, 30, 15, 10, 5, 1):
            self.cb_step.addItem(_t("{n} min/step").replace("{n}", str(m)), m)
        self.cb_step.setCurrentIndex(1)  # padrão 30
        layout.addRow(_t("Step per frame:"), self.cb_step)

        # Tamanho (viewport atual por padrão)
        vp = getattr(controller, "viewport", None)
        self._vp_w = vp.width() if vp else 1920
        self._vp_h = vp.height() if vp else 1080
        if self._vp_w <= 0: self._vp_w = 1920
        if self._vp_h <= 0: self._vp_h = 1080
        self._aspect = self._vp_w / self._vp_h if self._vp_h > 0 else 1.0

        self.sb_w = QSpinBox()
        self.sb_w.setRange(16, 7680)
        self.sb_w.setValue(self._vp_w)
        self.sb_w.setSuffix(" px")
        self.sb_h = QSpinBox()
        self.sb_h.setRange(16, 7680)
        self.sb_h.setValue(self._vp_h)
        self.sb_h.setSuffix(" px")

        linha = QHBoxLayout()
        linha.addWidget(QLabel(_t("W")))
        linha.addWidget(self.sb_w)
        linha.addWidget(QLabel(_t("x  H")))
        linha.addWidget(self.sb_h)
        holder = QWidget()
        holder.setLayout(linha)
        layout.addRow(_t("Size (W × H):"), holder)

        self.chk_lock = QCheckBox(_t("Keep aspect ratio"))
        self.chk_lock.setChecked(True)
        layout.addRow("", self.chk_lock)

        self.lbl_ff = QLabel("")
        self.lbl_ff.setWordWrap(True)
        layout.addRow("FFmpeg:", self.lbl_ff)
        self.btn_install_ff = QPushButton(_t("Download FFmpeg..."))
        self.btn_install_ff.clicked.connect(self._abrir_deps)
        layout.addRow("", self.btn_install_ff)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        self._atualizar_ffmpeg_status()

        # Conexões
        self.chk_lock.toggled.connect(self._update_lock_state)
        self.sb_w.valueChanged.connect(self._w_mudou)
        self.sb_h.valueChanged.connect(self._h_mudou)

        # Estado inicial
        self._update_lock_state(self.chk_lock.isChecked())

    def _update_lock_state(self, checked):
        self.sb_h.setEnabled(not checked)
        if checked:
            self._w_mudou(self.sb_w.value())

    def _w_mudou(self, val):
        if self.chk_lock.isChecked():
            self.sb_h.blockSignals(True)
            self.sb_h.setValue(max(16, int(round(val / self._aspect))))
            self.sb_h.blockSignals(False)

    def _h_mudou(self, val):
        if self.chk_lock.isChecked():
            self.sb_w.blockSignals(True)
            self.sb_w.setValue(max(16, int(round(val * self._aspect))))
            self.sb_w.blockSignals(False)

    def _abrir_deps(self):
        DependencyDialog(self).exec()
        self._atualizar_ffmpeg_status()

    def _atualizar_ffmpeg_status(self):
        p = _find_ffmpeg()
        if p:
            self.lbl_ff.setText(_t("Available") + "\n" + p)
            self.btn_install_ff.setVisible(False)
            self.cb_formato.model().item(1).setEnabled(True)
        else:
            self.lbl_ff.setText(_t("MISSING — required for MP4 video"))
            self.btn_install_ff.setVisible(True)
            self.cb_formato.model().item(1).setEnabled(False)

    def modo_saida(self):
        return "MP4" if self.cb_formato.currentIndex() == 1 else "PNG"

    def step_minutes(self):
        return self.cb_step.currentData()

    def tamanho(self):
        return int(self.sb_w.value()), int(self.sb_h.value())