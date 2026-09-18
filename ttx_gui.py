from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QSignalBlocker, Signal, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QPalette,
    QStandardItem,
    QStandardItemModel,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import ttx_converter as ttx

_HAS_QT = True

_APP_ICON_CANDIDATES = ("app_icon.ico", "app_icon.png")


def _app_icon() -> QIcon:
    """Load the app logo from ``assets/`` (falling back to where it is)."""
    here = Path(__file__).resolve().parent / "assets"
    for name in _APP_ICON_CANDIDATES:
        path = here / name
        if path.is_file():
            return QIcon(str(path))
    return QIcon()

MODE_DECODE = "decode"
MODE_ENCODE = "encode"
MODE_TSB = "tsb"
MODE_WAV_TSB = "wavtsb"
MODE_MP3 = "mp3"
MODE_FLAC = "flac"
MODE_OGG = "ogg"
MODE_TOC = "toc"

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tga")
FMT_LABELS = list(ttx.ENCODABLE_FORMATS.values())

MODES = (
    (MODE_DECODE, "TTX \u2192 PNG"),
    (MODE_ENCODE, "PNG \u2192 TTX"),
    (MODE_TSB, "TSB \u2192 WAV"),
    (MODE_WAV_TSB, "WAV \u2192 TSB"),
    (MODE_MP3, "MP3 \u2192 WAV"),
    (MODE_FLAC, "FLAC \u2192 WAV"),
    (MODE_OGG, "OGG \u2192 WAV"),
    (MODE_TOC, "TOC \u2192 JSON/TXT"),
)

CATEGORIES = (
    ("Textures", (MODE_DECODE, MODE_ENCODE)),
    ("Audio",    (MODE_TSB, MODE_WAV_TSB, MODE_MP3, MODE_FLAC, MODE_OGG)),
    ("Scenery",  (MODE_TOC,)),
)

MODE_LABELS = dict(MODES)
MODE_EXT = {
    MODE_DECODE: ".png",
    MODE_ENCODE: ".ttx",
    MODE_TSB: ".wav",
    MODE_WAV_TSB: ".tsb",
    MODE_MP3: ".wav",
    MODE_FLAC: ".wav",
    MODE_OGG: ".wav",
    MODE_TOC: ".json",
}
MODE_INPUT_EXTS = {
    MODE_DECODE: (".ttx",),
    MODE_ENCODE: IMAGE_EXT,
    MODE_TSB: (".tsb",),
    MODE_WAV_TSB: (".wav",),
    MODE_MP3: (".mp3",),
    MODE_FLAC: (".flac",),
    MODE_OGG: (".ogg",),
    MODE_TOC: (".toc",),
}
MODE_HINT = {
    MODE_DECODE: "Drag & drop .ttx files here\nor use the Browse button below",
    MODE_ENCODE: "Drag & drop PNG/JPG images here\nor use the Browse button below",
    MODE_TSB: "Drag & drop .tsb sound files here\nor use the Browse button below",
    MODE_WAV_TSB: "Drag & drop .wav files here\nor use the Browse button below",
    MODE_MP3: "Drag & drop .mp3 files here\nor use the Browse button below",
    MODE_FLAC: "Drag & drop .flac files here\nor use the Browse button below",
    MODE_OGG: "Drag & drop .ogg files here\nor use the Browse button below",
    MODE_TOC: "Drag & drop .toc scenery tables here\nor use the Browse button below",
}
MODE_VER = {
    MODE_DECODE: "Decodes DXT  ETC2  ASTC  R8  RGBA textures \u2192 PNG",
    MODE_ENCODE: "Encodes RGBA  R8  DXT1  DXT5  \u2192  .ttx (uncompressed)",
    MODE_TSB: "Decodes PCM sound (mono/stereo N-bit) \u2192 16-bit WAV",
    MODE_WAV_TSB: "Encodes uncompressed WAV \u2192 .tsb (mono16 stereo16 ...)",
    MODE_MP3: "Decodes MP3 \u2192 16-bit WAV (lossless PCM)",
    MODE_FLAC: "Decodes FLAC \u2192 16-bit WAV",
    MODE_OGG: "Decodes OGG Vorbis \u2192 16-bit WAV",
    MODE_TOC: "Decodes cultivation / xref scenery tables \u2192 JSON + text",
}
MODE_NOUN = {
    MODE_DECODE: "files",
    MODE_ENCODE: "images",
    MODE_TSB: "sounds",
    MODE_WAV_TSB: "WAV files",
    MODE_MP3: "MP3 files",
    MODE_FLAC: "FLAC files",
    MODE_OGG: "OGG files",
    MODE_TOC: "tables",
}
MODE_FILETYPES = {
    MODE_DECODE: [("TTX textures", "*.ttx")],
    MODE_ENCODE: [("Images", "*.png *.jpg *.jpeg *.bmp *.tga")],
    MODE_TSB: [("TSB sounds", "*.tsb")],
    MODE_WAV_TSB: [("WAV audio", "*.wav")],
    MODE_MP3: [("MP3 audio", "*.mp3")],
    MODE_FLAC: [("FLAC audio", "*.flac"), ("All audio", "*.flac *.wav *.ogg *.mp3")],
    MODE_OGG: [("OGG audio", "*.ogg")],
    MODE_TOC: [("TOC tables", "*.toc")],
}

DROP_BG = "#242424"
DROP_BG_HOVER = "#25313f"
LOG_BG = "#12151a"
ACCENT = "#0078d4"
ACCENT_HOVER = "#1a8ee8"
BG = "#1e1e1e"
FG = "#e0e0e0"

APP_QSS = """
QWidget { font-size: 10pt; }
QMainWindow, QWidget#central { background-color: #1e1e1e; }

QLabel { background: transparent; color: #e0e0e0; }
QLabel#header { font-size: 15pt; font-weight: 700; color: #ffffff; }
QLabel#muted  { font-size: 9pt; color: #7d7d7d; }
QLabel#counter { font-size: 9pt; color: #c0c0c0; }

QFrame#dropzone {
    background-color: #242424;
    border: 2px dashed #474747;
    border-radius: 8px;
}
QFrame#dropzone[hover="true"] {
    background-color: #25313f;
    border: 2px dashed #2f8ad8;
}
QLabel#hint { background: transparent; color: #9a9a9a; font-size: 11pt; }

QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
}
QPushButton:hover { background-color: #4c4c4c; }
QPushButton:pressed { background-color: #313131; }
QPushButton:disabled { color: #6f6f6f; background-color: #2a2a2a; }
QPushButton#accent { background-color: #0078d4; color: #ffffff; font-weight: 600; }
QPushButton#accent:hover { background-color: #1a8ee8; }
QPushButton#accent:disabled { background-color: #2a4a66; color: #93a9bb; }

QTextEdit#log {
    background-color: #12151a;
    color: #b4c0cc;
    border: 1px solid #303030;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #005a9e;
}

QToolTip {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #444444;
    padding: 4px;
}
QMenu { background-color: #2b2b2b; color: #e0e0e0; }
QMenu::item:selected { background-color: #0078d4; color: #ffffff; }
"""


def _dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(30, 30, 30))
    pal.setColor(QPalette.WindowText, QColor(224, 224, 224))
    pal.setColor(QPalette.Base, QColor(20, 20, 20))
    pal.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
    pal.setColor(QPalette.Text, QColor(224, 224, 224))
    pal.setColor(QPalette.PlaceholderText, QColor(136, 136, 136))
    pal.setColor(QPalette.Button, QColor(60, 60, 60))
    pal.setColor(QPalette.ButtonText, QColor(224, 224, 224))
    pal.setColor(QPalette.BrightText, QColor(255, 120, 120))
    pal.setColor(QPalette.Link, QColor(70, 150, 235))
    pal.setColor(QPalette.ToolTipBase, QColor(45, 45, 45))
    pal.setColor(QPalette.ToolTipText, QColor(224, 224, 224))
    pal.setColor(QPalette.Highlight, QColor(0, 120, 212))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                 QPalette.Highlight):
        pal.setColor(QPalette.Disabled, role, QColor(110, 110, 110))
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    return pal


class _ConvertWorker(QObject):
    """Runs conversions in a worker thread; talks to the GUI via signals."""

    log = Signal(str, str)
    progress = Signal(int, int)
    done = Signal(int, int)

    def __init__(self, files: list[str], mode: str, fmt: str, flip: bool):
        super().__init__()
        self._files = files
        self._mode = mode
        self._fmt = fmt
        self._flip = flip

    def run(self):
        ok = 0
        fail = 0
        total = len(self._files)
        for i, path in enumerate(self._files, 1):
            self.progress.emit(i, total)
            name = os.path.basename(path)
            out = os.path.splitext(path)[0] + MODE_EXT[self._mode]
            self.log.emit(
                f"[{i}/{total}] {name} \u2192 {os.path.basename(out)}", ""
            )
            try:

                def _st(msg):
                    self.log.emit(f"     {msg}", "dim")

                if self._mode == MODE_ENCODE:
                    res = ttx.encode_png(path, out, fmt=self._fmt,
                                         flip=self._flip, status=_st)
                    info = (f"{self._fmt}  {res['width']}x{res['height']}  "
                            f"mips=1  plain")
                elif self._mode == MODE_WAV_TSB:
                    import tsb_decoder

                    info_map = tsb_decoder.wav_to_tsb(path, out, status=_st)
                    info = (f"{info_map['format']}  "
                            f"{info_map['sample_rate']:.0f} Hz  "
                            f"{info_map['channels']}ch  {info_map['bits']}-bit  "
                            f"{info_map['frames']} frames")
                elif self._mode in (MODE_MP3, MODE_FLAC, MODE_OGG):
                    import audio_utils

                    info_map = audio_utils.audio_to_wav(path, out, status=_st)
                    info = (f"{info_map['source']}  "
                            f"{info_map['sample_rate']:.0f} Hz  "
                            f"{info_map['channels']}ch  16-bit WAV  "
                            f"{info_map['frames']} frames")
                elif self._mode == MODE_TSB:
                    import tsb_decoder

                    info_map = tsb_decoder.tsb_to_wav(path, out, status=_st)
                    info = (f"{info_map['format']}  "
                            f"{info_map['sample_rate']:.0f} Hz  "
                            f"{info_map['channels']}ch  {info_map['bits']}-bit")
                elif self._mode == MODE_TOC:
                    import toc_decoder

                    doc = toc_decoder.toc_to_json(path, out, status=_st)
                    info = (f"{doc['variant']}  "
                            f"placements={doc['placement_count']}")
                else:
                    res = ttx.ttx_to_png(path, out, flip=self._flip, status=_st)
                    info = (f"{res['format']}  {res['width']}x{res['height']}  "
                            f"mips={res['mips']}  "
                            f"{'compressed' if res['compressed'] else 'plain'}")
                self.log.emit(f"     {info}", "")
                self.log.emit(
                    f"     OK \u2192 {os.path.basename(out)}", "ok"
                )
                ok += 1
            except Exception as exc:
                self.log.emit(f"     ERROR: {exc}", "error")
                fail += 1
        self.done.emit(ok, fail)


class DropZone(QFrame):
    """Large drop target that highlights on hover."""

    dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self._hint = QLabel(MODE_HINT[MODE_DECODE], self)
        self._hint.setObjectName("hint")
        self._hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._hint)

    def set_hint(self, text: str):
        self._hint.setText(text)

    def _set_hover(self, on: bool):
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self._hint.setStyleSheet(
            "color: #cfe8ff;" if on else ""
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._set_hover(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_hover(False)
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            event.acceptProposedAction()
            self.dropped.emit(paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aerofly FS Converter")
        self.setWindowIcon(_app_icon())
        self.resize(760, 600)
        self.setMinimumSize(680, 500)

        self._files: list[str] = []
        self._busy = False
        self._mode = MODE_DECODE
        self._mode_combo: QComboBox | None = None
        self._fmt_combo: QComboBox | None = None
        self._flip_cb: QCheckBox | None = None
        self._drop: DropZone | None = None
        self._list_lbl: QLabel | None = None
        self._progress: QProgressBar | None = None
        self._convert_btn: QPushButton | None = None
        self._clear_btn: QPushButton | None = None
        self._open_btn: QPushButton | None = None
        self._thread: QThread | None = None
        self._worker: _ConvertWorker | None = None
        self._last_out_dir: str | None = None
        self._made = 0

        self.setAcceptDrops(True)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        header = QLabel("Aerofly FS Converter", central)
        header.setObjectName("header")
        root.addWidget(header)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("Convert:", central))
        combo = QComboBox(central)
        combo.setMinimumWidth(210)
        model = QStandardItemModel(combo)
        cat_font = QFont(combo.font())
        cat_font.setBold(True)
        for cat_name, mode_ids in CATEGORIES:
            cat = QStandardItem(cat_name)
            cat.setEnabled(False)
            cat.setFlags(Qt.NoItemFlags)
            cat.setSelectable(False)
            cat.setForeground(QColor("#8a8a8a"))
            cat.setFont(cat_font)
            model.appendRow(cat)
            for mid in mode_ids:
                item = QStandardItem(MODE_LABELS[mid])
                item.setData(mid, Qt.UserRole)
                model.appendRow(item)
        combo.setModel(model)
        combo.currentIndexChanged.connect(self._on_mode_changed)
        root.addLayout(mode_row)
        self._mode_combo = combo
        mode_row.addWidget(combo)
        mode_row.addStretch(1)

        self._ver_lbl = QLabel(MODE_VER[MODE_DECODE], central)
        self._ver_lbl.setObjectName("muted")
        root.addWidget(self._ver_lbl)

        zone = DropZone(central)
        zone.dropped.connect(self._add_files)
        root.addWidget(zone)
        self._drop = zone
        self.setAcceptDrops(True)

        pulse_row = QHBoxLayout()
        pulse_row.setSpacing(10)
        browse = QPushButton("Browse \u2026", central)
        browse.clicked.connect(self._browse)
        pulse_row.addWidget(browse)

        self._fmt_lbl = QLabel("Output format:", central)
        self._fmt_combo = QComboBox(central)
        for key, label in ttx.ENCODABLE_FORMATS.items():
            self._fmt_combo.addItem(label, key)
        pulse_row.addWidget(self._fmt_lbl)
        pulse_row.addWidget(self._fmt_combo)

        self._flip_cb = QCheckBox("Flip vertically", central)
        pulse_row.addWidget(self._flip_cb)

        pulse_row.addStretch(1)
        self._list_lbl = QLabel("No files selected", central)
        self._list_lbl.setObjectName("counter")
        pulse_row.addWidget(self._list_lbl)
        root.addLayout(pulse_row)

        self._log = QTextEdit(central)
        self._log.setObjectName("log")
        self._log.setReadOnly(True)
        self._log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        root.addWidget(self._log, 1)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)
        self._progress = QProgressBar(central)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)
        prog_row.addWidget(self._progress, 1)
        root.addLayout(prog_row)

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton("Open output folder", central)
        self._open_btn.clicked.connect(self._open_output)
        self._open_btn.setVisible(False)
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch(1)
        self._clear_btn = QPushButton("Clear", central)
        self._clear_btn.clicked.connect(self._clear_files)
        self._clear_btn.setDisabled(True)
        btn_row.addWidget(self._clear_btn)
        self._convert_btn = QPushButton("Convert", central)
        self._convert_btn.setObjectName("accent")
        self._convert_btn.clicked.connect(self._start_convert)
        self._convert_btn.setDisabled(True)
        btn_row.addWidget(self._convert_btn)
        root.addLayout(btn_row)

        self.setCentralWidget(central)
        self._set_mode(MODE_DECODE)

    # ------------------------------------------------------------------ Modes
    def _on_mode_changed(self, index: int):
        mode = self._mode_combo.itemData(index)
        if mode:
            self._set_mode(mode)

    def _set_mode(self, mode: str):
        if self._busy:
            if self._mode_combo:
                self._mode_combo.blockSignals(True)
                self._mode_combo.setCurrentIndex(
                    self._mode_combo.findData(self._mode)
                )
                self._mode_combo.blockSignals(False)
            return
        if mode != self._mode:
            self._clear_files()
        self._mode = mode
        if self._mode_combo:
            self._mode_combo.blockSignals(True)
            idx = self._mode_combo.findData(mode)
            if idx >= 0:
                self._mode_combo.setCurrentIndex(idx)
            self._mode_combo.blockSignals(False)
        self._ver_lbl.setText(MODE_VER[mode])
        if self._drop:
            self._drop.set_hint(MODE_HINT[mode])
        show_fmt = mode == MODE_ENCODE
        self._fmt_lbl.setVisible(show_fmt)
        self._fmt_combo.setVisible(show_fmt)
        self._flip_cb.setVisible(mode in (MODE_DECODE, MODE_ENCODE))

    # ------------------------------------------------------------------ Helpers
    def _append_log(self, text: str, tag: str = ""):
        color = {"dim": "#8a8a8a", "error": "#ff6b6b", "ok": "#8bc34a"}.get(
            tag, "#c4cfd9"
        )
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(text + "\n", fmt)
        self._log.setTextCursor(cur)
        self._log.ensureCursorVisible()

    def _set_counter(self, text: str, color: str = "#c0c0c0"):
        self._list_lbl.setText(text)
        self._list_lbl.setStyleSheet(f"color: {color};")

    def _selected_format(self) -> str:
        return self._fmt_combo.currentData()

    # ------------------------------------------------------------------ File handling
    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open files",
            "",
            ";;".join(f"{label} ({globs})" for label, globs in MODE_FILETYPES[self._mode]),
        )
        if paths:
            self._add_files(list(paths))

    def _accepts(self, path: str) -> bool:
        low = path.lower()
        return low.endswith(MODE_INPUT_EXTS[self._mode])

    def _add_files(self, paths: list[str]):
        if self._busy:
            return
        added = [p for p in paths if self._accepts(p)]
        if not added:
            label = MODE_FILETYPES[self._mode][0][0]
            self._append_log(f"No matching {label} found in the selection.", "error")
            return
        self._files.extend(added)
        noun = MODE_NOUN[self._mode]
        self._set_counter(f"{len(self._files)} {noun} selected")
        self._convert_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        for p in added:
            self._append_log(f"  {os.path.basename(p)}")

    def _clear_files(self):
        if self._busy:
            return
        self._files.clear()
        self._convert_btn.setDisabled(True)
        self._clear_btn.setDisabled(True)
        self._open_btn.setVisible(False)
        self._made = 0
        if self._progress:
            self._progress.setVisible(False)
            self._progress.setValue(0)
        self._set_counter("No files selected")
        self._log.clear()

    # ------------------------------------------------------------------ Convert
    def _start_convert(self):
        if self._busy or not self._files:
            return
        self._busy = True
        self._convert_btn.setDisabled(True)
        self._clear_btn.setDisabled(True)
        self._open_btn.setVisible(False)
        self._set_counter("Converting \u2026", ACCENT)
        if self._progress:
            self._progress.setRange(0, len(self._files))
            self._progress.setValue(0)
            self._progress.setVisible(True)

        self._thread = QThread(self)
        self._worker = _ConvertWorker(
            list(self._files), self._mode, self._selected_format(),
            self._flip_cb.isChecked(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._convert_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_progress(self, i: int, total: int):
        if self._progress:
            self._progress.setValue(i)
        self._set_counter(f"Converting  {i}/{total}  \u2026", ACCENT)

    def _convert_done(self, ok: int, fail: int):
        self._busy = False
        self._convert_btn.setEnabled(bool(self._files))
        self._clear_btn.setEnabled(bool(self._files))
        if self._progress:
            self._progress.setValue(self._progress.maximum())
        if fail:
            self._set_counter(
                f"Done \u2013 {ok} converted, {fail} failed", "#ff6b6b"
            )
        else:
            self._set_counter(
                f"Done \u2013 {ok} converted", "#8bc34a"
            )
        self._made = ok
        if self._files:
            self._last_out_dir = os.path.dirname(self._files[0])
        if self._made and self._last_out_dir:
            self._open_btn.setVisible(True)

    def _open_output(self):
        if self._last_out_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_out_dir))

    # ------------------------------------------------------------------ Drag & drop on window background
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            event.acceptProposedAction()
            self._add_files(paths)

    def closeEvent(self, event):
        if self._busy and self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)


def main():
    if not _HAS_QT:
        print("PySide6 not found - install with:  pip install PySide6")
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("Aerofly FS Converter")
    app.setWindowIcon(_app_icon())
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(APP_QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())