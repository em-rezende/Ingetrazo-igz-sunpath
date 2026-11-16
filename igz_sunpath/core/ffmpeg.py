# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: ffmpeg.py
# Descrição: Gerenciamento de FFmpeg e exportação de vídeo MP4.
# =========================================================================
import os
import shutil
import subprocess
import sys
import traceback
import urllib.request
import zipfile

from PySide6.QtCore import QStandardPaths, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QPlainTextEdit, QGridLayout, QFileDialog,
    QMessageBox,
)

from .i18n_loader import _t

# --- Configuração ------------------------------------------------------
_CONFIG_DIR = None


def _config_dir() -> str:
    global _CONFIG_DIR
    if _CONFIG_DIR:
        return _CONFIG_DIR
    base = ""
    try:
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    except Exception:
        pass
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".ingetrazo")
    _CONFIG_DIR = os.path.join(base, "igz_sunpath")
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    return _CONFIG_DIR


def _config_file() -> str:
    return os.path.join(_config_dir(), "config.json")


def load_config() -> dict:
    import json
    try:
        with open(_config_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(data: dict) -> None:
    import json
    try:
        d = _config_dir()
        tmp = _config_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _config_file())
    except Exception:
        traceback.print_exc()


def set_config_value(key, value) -> None:
    data = load_config()
    data[key] = value
    save_config(data)


def _ffmpeg_local_dir() -> str:
    return os.path.join(_config_dir(), "ffmpeg")


def _find_ffmpeg():
    cfg = load_config()
    p = cfg.get("ffmpeg_path")
    if p and os.path.isfile(p):
        return p
    p = shutil.which("ffmpeg")
    if p:
        return p

    # 1. Pasta do plugin
    local = _ffmpeg_local_dir()
    if os.path.isdir(local):
        for root, _, files in os.walk(local):
            for fn in files:
                if fn.lower() in ("ffmpeg.exe", "ffmpeg"):
                    return os.path.join(root, fn)

    # 2. Pasta do IngeTrazo (onde você instalou)
    base_appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    ingetrazo_ffmpeg = os.path.join(
        base_appdata, "ingetrazo", "IngeTrazo", "ffmpeg")
    if os.path.isdir(ingetrazo_ffmpeg):
        for root, _, files in os.walk(ingetrazo_ffmpeg):
            for fn in files:
                if fn.lower() in ("ffmpeg.exe", "ffmpeg"):
                    return os.path.join(root, fn)

    # 3. Locais comuns
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None

def _fps_str(fps):
    try:
        f = float(fps)
    except Exception:
        return "24"
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return ("%.6f" % f).rstrip("0").rstrip(".")


# --- Downloader --------------------------------------------------------
class FfmpegDownloadWorker(QThread):
    progresso = Signal(int, str)
    concluido = Signal(bool, str)

    URLS = [
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
    ]

    def __init__(self, dest_dir, parent=None):
        super().__init__(parent)
        self.dest_dir = dest_dir
        self._cancel = False

    def cancelar(self):
        self._cancel = True

    def _baixar(self, url, zip_path):
        req = urllib.request.Request(url, headers={"User-Agent": "igz_sunpath/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            lido = 0
            while True:
                if self._cancel:
                    raise RuntimeError(_t("canceled by user"))
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                lido += len(chunk)
                if total:
                    self.progresso.emit(int(lido * 100 / total), _t("Downloading FFmpeg..."))
                else:
                    self.progresso.emit(-1, _t("Downloading FFmpeg..."))

    def _extrair(self, zip_path):
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(self.dest_dir)
        for root, _, files in os.walk(self.dest_dir):
            for fn in files:
                if fn.lower() == "ffmpeg.exe":
                    return os.path.join(root, fn)
        return ""

    def run(self):
        os.makedirs(self.dest_dir, exist_ok=True)
        zip_path = os.path.join(self.dest_dir, "ffmpeg_download.zip")
        erros = []
        for url in self.URLS:
            if self._cancel:
                self.concluido.emit(False, _t("Canceled."))
                return
            try:
                self.progresso.emit(0, _t("Downloading from {host}...", host=url.split("/")[2]))
                self._baixar(url, zip_path)
                self.progresso.emit(-1, _t("Extracting..."))
                exe = self._extrair(zip_path)
                if exe:
                    set_config_value("ffmpeg_path", exe)
                    try:
                        os.remove(zip_path)
                    except Exception:
                        pass
                    self.concluido.emit(True, exe)
                    return
                erros.append(_t("{url}: ffmpeg.exe not found in the package", url=url))
            except Exception as exc:
                erros.append(f"{url}: {exc}")
        self.concluido.emit(False, "\n".join(erros) or _t("Download failed."))


# --- Diálogo de dependências ------------------------------------------
class DependencyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Video Dependencies"))
        self.resize(580, 440)
        self._dl_thread = None

        root = QVBoxLayout(self)
        intro = QLabel(
            _t("MP4 export uses <b>FFmpeg</b>.<br>Check the status below and download it if it is missing."))
        intro.setWordWrap(True)
        root.addWidget(intro)

        grid = QGridLayout()
        root.addLayout(grid)
        grid.addWidget(QLabel("<b>FFmpeg</b>"), 0, 0)
        self.lbl_ff = QLabel("")
        self.lbl_ff.setWordWrap(True)
        grid.addWidget(self.lbl_ff, 0, 1)
        caixa_ff = QHBoxLayout()
        self.btn_dl = QPushButton(_t("Download FFmpeg"))
        self.btn_dl.clicked.connect(self._baixar_ffmpeg)
        caixa_ff.addWidget(self.btn_dl)
        self.btn_local = QPushButton(_t("Browse..."))
        self.btn_local.clicked.connect(self._procurar_ffmpeg)
        caixa_ff.addWidget(self.btn_local)
        grid.addLayout(caixa_ff, 0, 2)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close, self)
        self.btn_refresh = btns.addButton(_t("Refresh status"), QDialogButtonBox.ActionRole)
        self.btn_refresh.clicked.connect(self._atualizar_status)
        self.btn_pasta = btns.addButton(_t("Open folder"), QDialogButtonBox.ActionRole)
        self.btn_pasta.clicked.connect(self._abrir_pasta)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)
        self._atualizar_status()

    def _append_log(self, text):
        if text:
            self.log.appendPlainText(str(text))

    def _atualizar_status(self):
        p = _find_ffmpeg()
        self.lbl_ff.setText((_t("Available") if p else _t("MISSING")) + (f"\n{p}" if p else ""))
        self.btn_dl.setEnabled(p is None)
        self._append_log(f"Status -> FFmpeg: {'OK' if p else _t('missing')}")

    def _baixar_ffmpeg(self):
        self._append_log(_t("Downloading FFmpeg... (may take a while / ~90 MB)"))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.btn_dl.setEnabled(False)
        self._dl_thread = FfmpegDownloadWorker(_ffmpeg_local_dir(), self)
        self._dl_thread.progresso.connect(self._dl_progresso)
        self._dl_thread.concluido.connect(self._dl_fim)
        self._dl_thread.start()

    def _dl_progresso(self, pct, msg):
        if pct < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
        if msg:
            self._append_log(msg)

    def _dl_fim(self, ok, msg):
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if ok else 0)
        self._append_log((_t("FFmpeg ready at: {path}", path=msg) if ok else _t("FFmpeg failure: {msg}", msg=str(msg))))
        self._atualizar_status()

    def _procurar_ffmpeg(self):
        base_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if not base_dir or not os.path.isdir(base_dir):
            base_dir = os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, _t("Select the ffmpeg executable"), base_dir,
            _t("FFmpeg (ffmpeg.exe ffmpeg);;All files (*.*)"))
        if path:
            set_config_value("ffmpeg_path", path)
            self._append_log(_t("FFmpeg set: {path}", path=path))
            self._atualizar_status()

    def _abrir_pasta(self):
        d = _ffmpeg_local_dir()
        try:
            os.makedirs(d, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(d)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            self._append_log(_t("Dependencies folder: {path}", path=d))

    def reject(self):
        if self._dl_thread is not None and self._dl_thread.isRunning():
            self._dl_thread.cancelar()
            self._dl_thread.wait(2000)
        super().reject()