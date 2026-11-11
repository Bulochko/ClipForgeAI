from __future__ import annotations
import json, os, shutil, subprocess, sys, uuid
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from ai_engine import run_analysis
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QFrame, QLineEdit,
    QDoubleSpinBox, QComboBox, QProgressBar, QMessageBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit, QAbstractItemView
)

APP_NAME = "ClipForge AI"


def prepare_workspace() -> tuple[Path, Path, Path]:
    preferred = Path.home() / "Videos" / "ClipForge AI"
    local_app_data = os.environ.get("LOCALAPPDATA")
    fallback_base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    candidates = (preferred, fallback_base / "ClipForge AI")
    errors = []

    for root in candidates:
        projects = root / "Projects"
        exports = root / "Exports"
        try:
            projects.mkdir(parents=True, exist_ok=True)
            exports.mkdir(parents=True, exist_ok=True)
            return root, projects, exports
        except OSError as exc:
            errors.append(f"{root}: {exc}")

    details = "\n".join(errors)
    raise RuntimeError(f"ĞĞµ ÑƒĞ´Ğ°Ğ»Ğ¾ÑÑŒ ÑĞ¾Ğ·Ğ´Ğ°Ñ‚ÑŒ Ñ€Ğ°Ğ±Ğ¾Ñ‡Ğ¸Ğµ Ğ¿Ğ°Ğ¿ĞºĞ¸ ClipForge AI. ĞŸÑ€Ğ¾Ğ²ĞµÑ€ÑŒ Ğ¿Ñ€Ğ°Ğ²Ğ° Ğ´Ğ¾ÑÑ‚ÑƒĞ¿Ğ°.\n{details}")


ROOT, PROJECTS, EXPORTS = prepare_workspace()


def find_bin(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    local = bundle_root / "tools" / exe
    if local.exists(): return str(local)
    return shutil.which(exe)


def probe_video(path: str) -> dict:
    ffprobe = find_bin("ffprobe")
    if not ffprobe: raise RuntimeError("ĞĞµ Ğ½Ğ°Ğ¹Ğ´ĞµĞ½ ffprobe. Ğ£ÑÑ‚Ğ°Ğ½Ğ¾Ğ²Ğ¸ FFmpeg Ğ¸ Ğ´Ğ¾Ğ±Ğ°Ğ²ÑŒ Ğ¿Ğ°Ğ¿ĞºÑƒ bin Ğ² PATH.")
    p = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "ĞĞµ ÑƒĞ´Ğ°Ğ»Ğ¾ÑÑŒ Ğ¿Ñ€Ğ¾Ñ‡Ğ¸Ñ‚Ğ°Ñ‚ÑŒ Ğ²Ğ¸Ğ´ĞµĞ¾")
    data = json.loads(p.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration": float(data.get("format", {}).get("duration", 0)), "width": video.get("width", 0), "height": video.get("height", 0), "fps": video.get("r_frame_rate", "â€”"), "codec": video.get("codec_name", "â€”")}


class RenderWorker(QThread):
    done = Signal(str)
    failed = Signal(str)
    progress = Signal(int)
    def __init__(self, source: str, start: float, end: float, output: str, ratio: str):
        super().__init__(); self.source=source; self.start_at=start; self.end_at=end; self.output=output; self.ratio=ratio
    def run(self):
        ffmpeg = find_bin("ffmpeg")
        if not ffmpeg: self.failed.emit("ĞĞµ Ğ½Ğ°Ğ¹Ğ´ĞµĞ½ ffmpeg. Ğ£ÑÑ‚Ğ°Ğ½Ğ¾Ğ²Ğ¸ FFmpeg Ğ¸ Ğ´Ğ¾Ğ±Ğ°Ğ²ÑŒ Ğ¿Ğ°Ğ¿ĞºÑƒ bin Ğ² PATH."); return
        if self.end_at <= self.start_at: self.failed.emit("Ğ’Ñ€ĞµĞ¼Ñ Ğ¾ĞºĞ¾Ğ½Ñ‡Ğ°Ğ½Ğ¸Ñ Ğ´Ğ¾Ğ»Ğ¶Ğ½Ğ¾ Ğ±Ñ‹Ñ‚ÑŒ Ğ±Ğ¾Ğ»ÑŒÑˆĞµ Ğ²Ñ€ĞµĞ¼ĞµĞ½Ğ¸ Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ°."); return
        if self.ratio == "9:16": filt="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        elif self.ratio == "1:1": filt="scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
        else: filt="scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
        encoder_probe = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
        available = (encoder_probe.stdout or "") + (encoder_probe.stderr or "")
        if "h264_nvenc" in available:
            video_codec = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21"]
        elif "libx264" in available:
            video_codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        elif "libopenh264" in available:
            video_codec = ["-c:v", "libopenh264", "-b:v", "6M"]
        else:
            video_codec = ["-c:v", "mpeg4", "-q:v", "3"]
        cmd=[ffmpeg,"-y","-ss",str(self.start_at),"-i",self.source,"-t",str(self.end_at-self.start_at),"-vf",filt,*video_codec,"-c:a","aac","-b:a","192k","-movflags","+faststart",self.output]
        p=subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode: self.failed.emit(p.stderr[-1800:] or "ĞÑˆĞ¸Ğ±ĞºĞ° FFmpeg")
        else: self.done.emit(self.output)


class AIAnalysisWorker(QThread):
    completed = Signal(object, object, str)
    failed = Signal(str)
    def __init__(self, path: str, duration: float, whisper_model: str):
        super().__init__(); self.path=path; self.duration=duration; self.whisper_model=whisper_model
    def run(self):
        try:
            segments, clips, info = run_analysis(self.path, self.duration, self.whisper_model)
            self.completed.emit(segments, clips, info)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1180, 760); self.setMinimumSize(900, 620)
        self.current_video=None; self.video_info=None; self.worker=None; self.ai_worker=None; self.ai_clips=[]; self.transcript_segments=[]
        self.setStyleSheet("""
        QWidget { background:#111318; color:#e9edf5; font-family:'Segoe UI'; font-size:10pt; }
        QFrame#Panel { background:#191d25; border:1px solid #2a303b; border-radius:12px; }
        QLabel#Muted { color:#9aa4b2; }
        QLabel#Brand { color:#ffffff; font-size:22pt; font-weight:700; }
        QPushButton { background:#252c38; border:1px solid #343e4d; border-radius:8px; padding:10px 14px; }
        QPushButton:hover { background:#303a49; }
        QPushButton#Primary { background:#7457ff; border:0; color:white; font-weight:600; }
        QPushButton#Primary:hover { background:#846cff; }
        QLineEdit,QDoubleSpinBox,QComboBox,QTextEdit,QListWidget,QTableWidget { background:#141820; border:1px solid #303846; border-radius:7px; padding:7px; selection-background-color:#5742c5; }
        QHeaderView::section { background:#202631; color:#aeb8c6; padding:8px; border:0; }
        QProgressBar { background:#252c38; border:0; border-radius:5px; height:9px; text-align:center; }
        QProgressBar::chunk { background:#7457ff; border-radius:5px; }
        QTabWidget::pane { border:1px solid #2a303b; border-radius:10px; }
        QTabBar::tab { background:#191d25; padding:11px 18px; border-top-left-radius:7px; border-top-right-radius:7px; color:#9aa4b2; }
        QTabBar::tab:selected { background:#29233f; color:white; }
        """)
        self.build_ui(); self.refresh_exports(); self.check_ffmpeg()

    def panel(self):
        f=QFrame(); f.setObjectName("Panel"); l=QVBoxLayout(f); l.setContentsMargins(18,16,18,16); l.setSpacing(10); return f,l

    def build_ui(self):
        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root); main.setContentsMargins(24,20,24,20); main.setSpacing(16)
        top=QHBoxLayout(); brand=QLabel("ClipForge AI"); brand.setObjectName("Brand"); top.addWidget(brand); top.addWidget(QLabel("LOCAL VIDEO STUDIO")); top.addStretch(); self.status=QLabel("ĞŸÑ€Ğ¾Ğ²ĞµÑ€ĞºĞ° ĞºĞ¾Ğ¼Ğ¿Ğ¾Ğ½ĞµĞ½Ñ‚Ğ¾Ğ²â€¦"); self.status.setObjectName("Muted"); top.addWidget(self.status); main.addLayout(top)
        intro=QLabel("ĞŸÑ€ĞµĞ²Ñ€Ğ°Ñ‰Ğ°Ğ¹ Ğ´Ğ»Ğ¸Ğ½Ğ½Ñ‹Ğµ Ğ²Ğ¸Ğ´ĞµĞ¾ Ğ² Ğ²ĞµÑ€Ñ‚Ğ¸ĞºĞ°Ğ»ÑŒĞ½Ñ‹Ğµ ĞºĞ»Ğ¸Ğ¿Ñ‹ â€” Ğ¿Ñ€ÑĞ¼Ğ¾ Ğ½Ğ° ÑĞ²Ğ¾Ñ‘Ğ¼ ĞºĞ¾Ğ¼Ğ¿ÑŒÑÑ‚ĞµÑ€Ğµ."); intro.setObjectName("Muted"); main.addWidget(intro)
        tabs=QTabWidget(); main.addWidget(tabs)
        home=QWidget(); h=QVBoxLayout(home); h.setContentsMargins(14,14,14,14); h.setSpacing(14)
        row=QHBoxLayout(); left, ll=self.panel(); ll.addWidget(QLabel("Ğ˜Ğ¡Ğ¥ĞĞ”ĞĞĞ• Ğ’Ğ˜Ğ”Ğ•Ğ")); self.file_label=QLabel("Ğ’Ğ¸Ğ´ĞµĞ¾ ĞµÑ‰Ñ‘ Ğ½Ğµ Ğ²Ñ‹Ğ±Ñ€Ğ°Ğ½Ğ¾"); self.file_label.setWordWrap(True); self.file_label.setStyleSheet("font-size:14pt;font-weight:600"); ll.addWidget(self.file_label); self.meta=QLabel("Ğ”Ğ¾Ğ±Ğ°Ğ²ÑŒ Ğ²Ğ¸Ğ´ĞµĞ¾Ñ„Ğ°Ğ¹Ğ», Ñ‡Ñ‚Ğ¾Ğ±Ñ‹ ÑƒĞ²Ğ¸Ğ´ĞµÑ‚ÑŒ ĞµĞ³Ğ¾ Ğ¿Ğ°Ñ€Ğ°Ğ¼ĞµÑ‚Ñ€Ñ‹."); self.meta.setObjectName("Muted"); self.meta.setWordWrap(True); ll.addWidget(self.meta); choose=QPushButton("ï¼‹  Ğ”Ğ¾Ğ±Ğ°Ğ²Ğ¸Ñ‚ÑŒ Ğ²Ğ¸Ğ´ĞµĞ¾"); choose.setObjectName("Primary"); choose.clicked.connect(self.choose_video); ll.addWidget(choose); row.addWidget(left,2)
        right,rl=self.panel(); rl.addWidget(QLabel("Ğ‘Ğ«Ğ¡Ğ¢Ğ ĞĞ• Ğ”Ğ•Ğ™Ğ¡Ğ¢Ğ’Ğ˜Ğ•")); rl.addWidget(QLabel("Ğ¡Ğ¾Ğ·Ğ´Ğ°Ñ‚ÑŒ ĞºĞ»Ğ¸Ğ¿")); rl.addWidget(QLabel("Ğ’Ñ‹Ğ±ĞµÑ€Ğ¸ Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ¾ Ğ¸ ĞºĞ¾Ğ½ĞµÑ† Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚Ğ°, Ñ„Ğ¾Ñ€Ğ¼Ğ°Ñ‚ Ğ¸ Ğ½Ğ°Ğ¶Ğ¼Ğ¸ Â«Ğ ĞµĞ½Ğ´ĞµÑ€Ğ¸Ñ‚ÑŒÂ».")); self.start_spin=QDoubleSpinBox(); self.start_spin.setRange(0,999999); self.start_spin.setDecimals(2); self.start_spin.setSuffix(" ÑĞµĞº â€” Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ¾"); self.end_spin=QDoubleSpinBox(); self.end_spin.setRange(0,999999); self.end_spin.setDecimals(2); self.end_spin.setValue(30); self.end_spin.setSuffix(" ÑĞµĞº â€” ĞºĞ¾Ğ½ĞµÑ†"); rl.addWidget(self.start_spin); rl.addWidget(self.end_spin); self.ratio=QComboBox(); self.ratio.addItems(["9:16 â€” YouTube Shorts / Reels / TikTok","1:1 â€” ĞºĞ²Ğ°Ğ´Ñ€Ğ°Ñ‚","16:9 â€” Ğ³Ğ¾Ñ€Ğ¸Ğ·Ğ¾Ğ½Ñ‚Ğ°Ğ»ÑŒĞ½Ğ¾Ğµ"]); rl.addWidget(self.ratio); self.render_btn=QPushButton("Ğ ĞµĞ½Ğ´ĞµÑ€Ğ¸Ñ‚ÑŒ ĞºĞ»Ğ¸Ğ¿"); self.render_btn.setObjectName("Primary"); self.render_btn.clicked.connect(self.render_clip); rl.addWidget(self.render_btn); self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); rl.addWidget(self.progress); row.addWidget(right,3); h.addLayout(row)
        bottom=QHBoxLayout(); exp,el=self.panel(); el.addWidget(QLabel("ĞŸĞĞ¡Ğ›Ğ•Ğ”ĞĞ˜Ğ• Ğ­ĞšĞ¡ĞŸĞĞ Ğ¢Ğ«")); self.exports=QListWidget(); el.addWidget(self.exports); bottom.addWidget(exp,2); notes,nl=self.panel(); nl.addWidget(QLabel("Ğ¡Ğ›Ğ•Ğ”Ğ£Ğ®Ğ©Ğ˜Ğ• Ğ’ĞĞ—ĞœĞĞ–ĞĞĞ¡Ğ¢Ğ˜")); nl.addWidget(QLabel("â€¢ AI-Ğ¿Ğ¾Ğ¸ÑĞº Ğ»ÑƒÑ‡ÑˆĞ¸Ñ… Ğ¼Ğ¾Ğ¼ĞµĞ½Ñ‚Ğ¾Ğ²\nâ€¢ ĞĞ²Ñ‚Ğ¾Ğ¼Ğ°Ñ‚Ğ¸Ñ‡ĞµÑĞºĞ¸Ğµ ÑÑƒĞ±Ñ‚Ğ¸Ñ‚Ñ€Ñ‹\nâ€¢ ĞŸĞ°ĞºĞµÑ‚Ğ½Ğ°Ñ Ğ½Ğ°Ñ€ĞµĞ·ĞºĞ°\nâ€¢ Ğ¨Ğ°Ğ±Ğ»Ğ¾Ğ½Ñ‹ Ğ¾Ñ„Ğ¾Ñ€Ğ¼Ğ»ĞµĞ½Ğ¸Ñ\nâ€¢ Ğ ÑƒÑ‡Ğ½Ğ°Ñ Ğ²Ñ€ĞµĞ¼ĞµĞ½Ğ½Ğ°Ñ ÑˆĞºĞ°Ğ»Ğ°")); nl.addStretch(); nl.addWidget(QLabel("Ğ­Ñ‚Ğ¾ ÑÑ‚Ğ°Ñ€Ñ‚Ğ¾Ğ²Ğ°Ñ Ğ»Ğ¾ĞºĞ°Ğ»ÑŒĞ½Ğ°Ñ Ğ²ĞµÑ€ÑĞ¸Ñ. AI-Ğ°Ğ½Ğ°Ğ»Ğ¸Ğ· Ğ¸ Ñ€Ğ°ÑÑˆĞ¸Ñ€ĞµĞ½Ğ½Ñ‹Ğ¹ Ğ¼Ğ¾Ğ½Ñ‚Ğ°Ğ¶ Ğ±ÑƒĞ´ÑƒÑ‚ Ğ´Ğ¾Ğ±Ğ°Ğ²Ğ»ĞµĞ½Ñ‹ ÑĞ»ĞµĞ´ÑƒÑÑ‰Ğ¸Ğ¼Ğ¸ ÑÑ‚Ğ°Ğ¿Ğ°Ğ¼Ğ¸."),0); bottom.addWidget(notes,1); h.addLayout(bottom); tabs.addTab(home,"ĞĞ±Ğ·Ğ¾Ñ€")
        library=QWidget(); lv=QVBoxLayout(library); lv.addWidget(QLabel("Ğ¤Ğ°Ğ¹Ğ»Ñ‹, ĞºĞ¾Ñ‚Ğ¾Ñ€Ñ‹Ğµ Ñ‚Ñ‹ ÑĞºÑĞ¿Ğ¾Ñ€Ñ‚Ğ¸Ñ€Ğ¾Ğ²Ğ°Ğ» Ğ¸Ğ· ClipForge AI.")); self.export_table=QTableWidget(0,2); self.export_table.setHorizontalHeaderLabels(["Ğ¤Ğ°Ğ¹Ğ»","Ğ Ğ°ÑĞ¿Ğ¾Ğ»Ğ¾Ğ¶ĞµĞ½Ğ¸Ğµ"]); self.export_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.export_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch); lv.addWidget(self.export_table); open_folder=QPushButton("ĞÑ‚ĞºÑ€Ñ‹Ñ‚ÑŒ Ğ¿Ğ°Ğ¿ĞºÑƒ ÑĞºÑĞ¿Ğ¾Ñ€Ñ‚Ğ°"); open_folder.clicked.connect(lambda: os.startfile(str(EXPORTS)) if os.name=="nt" else None); lv.addWidget(open_folder); tabs.addTab(library,"Ğ­ĞºÑĞ¿Ğ¾Ñ€Ñ‚Ñ‹")
        ai=QWidget(); av=QVBoxLayout(ai); av.setContentsMargins(14,14,14,14); av.setSpacing(12)
        ai_info, ail=self.panel(); ail.addWidget(QLabel("AI VIDEO ANALYZER")); ail.addWidget(QLabel("Ğ›Ğ¾ĞºĞ°Ğ»ÑŒĞ½Ğ°Ñ Ñ€Ğ°ÑÑˆĞ¸Ñ„Ñ€Ğ¾Ğ²ĞºĞ° Ñ€ĞµÑ‡Ğ¸ Ğ¸ Ğ¿Ğ¾Ğ¸ÑĞº ÑĞ°Ğ¼Ğ¾ÑÑ‚Ğ¾ÑÑ‚ĞµĞ»ÑŒĞ½Ñ‹Ñ… Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚Ğ¾Ğ² Ğ´Ğ»Ñ Shorts. Ğ¡Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ° ÑƒÑÑ‚Ğ°Ğ½Ğ¾Ğ²Ğ¸ AI-ĞºĞ¾Ğ¼Ğ¿Ğ¾Ğ½ĞµĞ½Ñ‚Ñ‹ Ñ‡ĞµÑ€ĞµĞ· INSTALL_AI.bat.")); av.addWidget(ai_info)
        controls=QHBoxLayout(); self.whisper_choice=QComboBox(); self.whisper_choice.addItems(["small â€” Ğ±Ñ‹ÑÑ‚Ñ€ĞµĞµ, Ñ€ĞµĞºĞ¾Ğ¼ĞµĞ½Ğ´Ğ¾Ğ²Ğ°Ğ½Ğ¾", "medium â€” Ñ‚Ğ¾Ñ‡Ğ½ĞµĞµ, Ğ¼ĞµĞ´Ğ»ĞµĞ½Ğ½ĞµĞµ", "large-v3-turbo â€” Ğ¼Ğ°ĞºÑĞ¸Ğ¼Ğ°Ğ»ÑŒĞ½Ğ¾Ğµ ĞºĞ°Ñ‡ĞµÑÑ‚Ğ²Ğ¾"])
        self.ai_run_btn=QPushButton("ĞĞ½Ğ°Ğ»Ğ¸Ğ·Ğ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒ Ñ‚ĞµĞºÑƒÑ‰ĞµĞµ Ğ²Ğ¸Ğ´ĞµĞ¾"); self.ai_run_btn.setObjectName("Primary"); self.ai_run_btn.clicked.connect(self.start_ai_analysis); controls.addWidget(self.whisper_choice,2); controls.addWidget(self.ai_run_btn,1); av.addLayout(controls)
        self.ai_progress=QProgressBar(); self.ai_progress.setRange(0,0); self.ai_progress.hide(); av.addWidget(self.ai_progress)
        self.ai_status=QLabel("ĞĞ¶Ğ¸Ğ´Ğ°Ğ½Ğ¸Ğµ Ğ²Ğ¸Ğ´ĞµĞ¾. ĞĞ½Ğ°Ğ»Ğ¸Ğ· Ğ²Ñ‹Ğ¿Ğ¾Ğ»Ğ½ÑĞµÑ‚ÑÑ Ğ»Ğ¾ĞºĞ°Ğ»ÑŒĞ½Ğ¾."); self.ai_status.setObjectName("Muted"); av.addWidget(self.ai_status)
        self.ai_table=QTableWidget(0,5); self.ai_table.setHorizontalHeaderLabels(["ĞÑ†ĞµĞ½ĞºĞ°","ĞĞ°Ğ·Ğ²Ğ°Ğ½Ğ¸Ğµ","ĞĞ°Ñ‡Ğ°Ğ»Ğ¾","ĞšĞ¾Ğ½ĞµÑ†","ĞŸĞ¾Ñ‡ĞµĞ¼Ñƒ Ğ²Ñ‹Ğ±Ñ€Ğ°Ğ½Ğ¾"]); self.ai_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.ai_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch); self.ai_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.ai_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.ai_table.cellDoubleClicked.connect(self.select_ai_clip); av.addWidget(self.ai_table)
        ai_actions=QHBoxLayout(); self.use_clip_btn=QPushButton("Ğ˜ÑĞ¿Ğ¾Ğ»ÑŒĞ·Ğ¾Ğ²Ğ°Ñ‚ÑŒ Ğ²Ñ‹Ğ±Ñ€Ğ°Ğ½Ğ½Ñ‹Ğ¹ Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚"); self.use_clip_btn.clicked.connect(self.use_selected_ai_clip); ai_actions.addWidget(self.use_clip_btn); ai_actions.addStretch(); av.addLayout(ai_actions); av.addStretch(); tabs.addTab(ai,"AI Analyzer")
        settings=QWidget(); sv=QVBoxLayout(settings); sv.addWidget(QLabel("Ğ›Ğ¾ĞºĞ°Ğ»ÑŒĞ½Ñ‹Ğµ Ğ½Ğ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ¸")); sv.addWidget(QLabel(f"Ğ Ğ°Ğ±Ğ¾Ñ‡Ğ°Ñ Ğ¿Ğ°Ğ¿ĞºĞ°: {ROOT}")); sv.addWidget(QLabel("FFmpeg Ğ¸ FFprobe Ğ´Ğ¾Ğ»Ğ¶Ğ½Ñ‹ Ğ±Ñ‹Ñ‚ÑŒ Ğ´Ğ¾ÑÑ‚ÑƒĞ¿Ğ½Ñ‹ Ñ‡ĞµÑ€ĞµĞ· PATH Ğ¸Ğ»Ğ¸ Ğ»ĞµĞ¶Ğ°Ñ‚ÑŒ Ğ² Ğ¿Ğ°Ğ¿ĞºĞµ tools Ñ€ÑĞ´Ğ¾Ğ¼ Ñ Ğ¿Ñ€Ğ¾Ğ³Ñ€Ğ°Ğ¼Ğ¼Ğ¾Ğ¹.")); sv.addStretch(); tabs.addTab(settings,"ĞĞ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ¸")
        foot=QLabel("CLIPFORGE AI  â€¢  WINDOWS FULL BUILD  â€¢  0.3.0"); foot.setObjectName("Muted"); main.addWidget(foot)

    def check_ffmpeg(self):
        ok=find_bin("ffmpeg") and find_bin("ffprobe")
        self.status.setText("â— FFmpeg Ğ³Ğ¾Ñ‚Ğ¾Ğ²" if ok else "â— Ğ¢Ñ€ĞµĞ±ÑƒĞµÑ‚ÑÑ FFmpeg")
        self.status.setStyleSheet("color:#66d9a3" if ok else "color:#ffbd69")

    def choose_video(self):
        path,_=QFileDialog.getOpenFileName(self,"Ğ’Ñ‹Ğ±Ñ€Ğ°Ñ‚ÑŒ Ğ¸ÑÑ…Ğ¾Ğ´Ğ½Ğ¾Ğµ Ğ²Ğ¸Ğ´ĞµĞ¾","", "Ğ’Ğ¸Ğ´ĞµĞ¾ (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;Ğ’ÑĞµ Ñ„Ğ°Ğ¹Ğ»Ñ‹ (*.*)")
        if not path: return
        try: info=probe_video(path)
        except Exception as e: QMessageBox.critical(self,"ĞĞµ ÑƒĞ´Ğ°Ğ»Ğ¾ÑÑŒ Ğ¾Ñ‚ĞºÑ€Ñ‹Ñ‚ÑŒ Ğ²Ğ¸Ğ´ĞµĞ¾",str(e)); return
        self.current_video=path; self.video_info=info; self.file_label.setText(Path(path).name)
        self.meta.setText(f"{info['width']} Ã— {info['height']} px  â€¢  {self.fmt(info['duration'])}  â€¢  {info['codec']}  â€¢  {Path(path).stat().st_size/1024/1024:.1f} MB")
        self.start_spin.setValue(0); self.end_spin.setValue(min(30,info['duration']))

    @staticmethod
    def fmt(seconds):
        s=int(seconds); return f"{s//3600:02}:{(s%3600)//60:02}:{s%60:02}"

    def render_clip(self):
        if not self.current_video: QMessageBox.information(self,"ĞÑƒĞ¶Ğ½Ğ¾ Ğ²Ğ¸Ğ´ĞµĞ¾","Ğ¡Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ° Ğ´Ğ¾Ğ±Ğ°Ğ²ÑŒ Ğ¸ÑÑ…Ğ¾Ğ´Ğ½Ğ¾Ğµ Ğ²Ğ¸Ğ´ĞµĞ¾."); return
        start=self.start_spin.value(); end=self.end_spin.value()
        if end<=start: QMessageBox.warning(self,"ĞŸÑ€Ğ¾Ğ²ĞµÑ€ÑŒ Ñ‚Ğ°Ğ¹Ğ¼ĞºĞ¾Ğ´","Ğ’Ñ€ĞµĞ¼Ñ Ğ¾ĞºĞ¾Ğ½Ñ‡Ğ°Ğ½Ğ¸Ñ Ğ´Ğ¾Ğ»Ğ¶Ğ½Ğ¾ Ğ±Ñ‹Ñ‚ÑŒ Ğ±Ğ¾Ğ»ÑŒÑˆĞµ Ğ²Ñ€ĞµĞ¼ĞµĞ½Ğ¸ Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ°."); return
        if self.video_info and end>self.video_info['duration']+0.1: QMessageBox.warning(self,"ĞŸÑ€Ğ¾Ğ²ĞµÑ€ÑŒ Ñ‚Ğ°Ğ¹Ğ¼ĞºĞ¾Ğ´","ĞšĞ¾Ğ½ĞµÑ† Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚Ğ° Ğ²Ñ‹Ñ…Ğ¾Ğ´Ğ¸Ñ‚ Ğ·Ğ° Ğ´Ğ»Ğ¸Ñ‚ĞµĞ»ÑŒĞ½Ğ¾ÑÑ‚ÑŒ Ğ¸ÑÑ…Ğ¾Ğ´Ğ½Ğ¾Ğ³Ğ¾ Ğ²Ğ¸Ğ´ĞµĞ¾."); return
        ratio="9:16" if self.ratio.currentIndex()==0 else ("1:1" if self.ratio.currentIndex()==1 else "16:9")
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); output=str(EXPORTS/f"clip_{stamp}_{uuid.uuid4().hex[:4]}.mp4")
        self.render_btn.setEnabled(False); self.progress.show()
        self.worker=RenderWorker(self.current_video,start,end,output,ratio); self.worker.done.connect(self.render_done); self.worker.failed.connect(self.render_failed); self.worker.start()

    def start_ai_analysis(self):
        if not self.current_video or not self.video_info:
            QMessageBox.information(self, "ĞÑƒĞ¶Ğ½Ğ¾ Ğ²Ğ¸Ğ´ĞµĞ¾", "Ğ¡Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ° Ğ´Ğ¾Ğ±Ğ°Ğ²ÑŒ Ğ¸ÑÑ…Ğ¾Ğ´Ğ½Ğ¾Ğµ Ğ²Ğ¸Ğ´ĞµĞ¾ Ğ½Ğ° Ğ²ĞºĞ»Ğ°Ğ´ĞºĞµ Â«ĞĞ±Ğ·Ğ¾Ñ€Â»."); return
        if self.ai_worker and self.ai_worker.isRunning(): return
        model = "small" if self.whisper_choice.currentIndex()==0 else ("medium" if self.whisper_choice.currentIndex()==1 else "large-v3-turbo")
        self.ai_run_btn.setEnabled(False); self.ai_progress.show(); self.ai_status.setText("Ğ Ğ°ÑÑˆĞ¸Ñ„Ñ€Ğ¾Ğ²ĞºĞ° Ñ€ĞµÑ‡Ğ¸ Ğ¸ Ğ¿Ğ¾Ğ¸ÑĞº Ğ»ÑƒÑ‡ÑˆĞ¸Ñ… Ğ¼Ğ¾Ğ¼ĞµĞ½Ñ‚Ğ¾Ğ²â€¦ ĞŸĞµÑ€Ğ²Ñ‹Ğ¹ Ğ·Ğ°Ğ¿ÑƒÑĞº Ğ¼Ğ¾Ğ¶ĞµÑ‚ ÑĞºĞ°Ñ‡Ğ°Ñ‚ÑŒ Ğ¼Ğ¾Ğ´ĞµĞ»ÑŒ.")
        self.ai_worker=AIAnalysisWorker(self.current_video, self.video_info["duration"], model)
        self.ai_worker.completed.connect(self.ai_analysis_done); self.ai_worker.failed.connect(self.ai_analysis_failed); self.ai_worker.start()

    def ai_analysis_done(self, segments, clips, info):
        self.ai_run_btn.setEnabled(True); self.ai_progress.hide(); self.transcript_segments=segments; self.ai_clips=clips
        self.ai_status.setText(f"Ğ“Ğ¾Ñ‚Ğ¾Ğ²Ğ¾: Ğ½Ğ°Ğ¹Ğ´ĞµĞ½Ğ¾ {len(clips)} Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚Ğ¾Ğ²; Ñ€Ğ°ÑĞ¿Ğ¾Ğ·Ğ½Ğ°Ğ½Ğ¾ ÑĞµĞ³Ğ¼ĞµĞ½Ñ‚Ğ¾Ğ² Ñ€ĞµÑ‡Ğ¸: {len(segments)}. {info}")
        self.ai_table.setRowCount(len(clips))
        for i,c in enumerate(clips):
            values=[str(c.get("score", "â€”")), c.get("title", c.get("reason", "AI clip")), self.fmt(c["start"]), self.fmt(c["enuëm¢G§²ÚîÆ­yÑ¥É•Ñ½Éä€‰™™µÁ•œ¹•á”ˆ(€€€€‘™ÁÉ½‰•A…Ñ €ô)½¥¸µA…Ñ €‘¥É•Ñ½Éä€‰™™ÁÉ½‰”¹•á”ˆ(€€€™½É•… € ‘A…Ñ ¥¸  ‘™µÁ•A…Ñ °€‘™ÁÉ½‰•A…Ñ ¤¤ì(€€€€€€€¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘A…Ñ €µA…Ñ¡QåÁ”1•…˜¤¤ì(€€€€€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°¥Ìµ¥ÍÍ¥¹œÉ•ÅÕ¥É••á•ÕÑ…‰±”è€‘A…Ñ ˆ(€€€€€€€ô(€€€ô((€€€™½É•… € ‘A…Ñ ¥¸  ‘™µÁ•A…Ñ °€‘™ÁÉ½‰•A…Ñ ¤¤ì(€€€€€€€€‘5…¡¥¹”€ô•ĞµA•5…¡¥¹”€µA…Ñ €‘A…Ñ (€€€€€€€¥˜€ ‘5…¡¥¹”€µ¹”€ÁààØØĞ¤ì(€€€€€€€€€€€€‘5…¡¥¹•!•à€ô€ˆÁáìÀé`Ñôˆ€µ˜€‘5…¡¥¹”(€€€€€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°½¹Ñ…¥¹Ì„¹½¸µàØĞ•á•ÕÑ…‰±”€ ‘5…¡¥¹•!•à¤è€‘A…Ñ ˆ(€€€€€€€ô(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°½¹Ñ…¥¹ÌàØĞµÁ•œ…¹ÁÉ½‰”•á•ÕÑ…‰±•Ì¸ˆ((€€€€‘Y•ÉÍ¥½¹=ÕÑÁÕĞ€ô%¹Ù½­”µ¡•­•‘9…Ñ¥Ù”€µá•ÕÑ…‰±”€‘™µÁ•A…Ñ €µÉÕµ•¹ÑÌ  ˆµÙ•ÉÍ¥½¸ˆ¤€µ•ÍÉ¥ÁÑ¥½¸€ˆ‘1…‰•°™™µÁ•œ€µÙ•ÉÍ¥½¸ˆ(€€€¥˜€ ‘Y•ÉÍ¥½¹=ÕÑÁÕĞ€µ¹½Ñµ…Ñ €ˆ ı´¥y™™µÁ•œÙ•ÉÍ¥½¸€ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°™™µÁ•œ€µÙ•ÉÍ¥½¸É•ÑÕÉ¹•ÍÕ•ÍÌ‰ÕĞ‘¥¹½Ğ¥‘•¹Ñ¥™äµÁ•œ¸ˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°€   ‘Y•ÉÍ¥½¹=ÕÑÁÕĞ¹QÉ¥´ ¤€µÍÁ±¥Ğ€‰Èı¸ˆ¥lÁt¤¤ˆ((€€€€‘™ÁÉ½‰•Y•ÉÍ¥½¸€ô%¹Ù½­”µ¡•­•‘9…Ñ¥Ù”€µá•ÕÑ…‰±”€‘™ÁÉ½‰•A…Ñ €µÉÕµ•¹ÑÌ  ˆµÙ•ÉÍ¥½¸ˆ¤€µ•ÍÉ¥ÁÑ¥½¸€ˆ‘1…‰•°™™ÁÉ½‰”€µÙ•ÉÍ¥½¸ˆ(€€€¥˜€ ‘™ÁÉ½‰•Y•ÉÍ¥½¸€µ¹½Ñµ…Ñ €ˆ ı´¥y™™ÁÉ½‰”Ù•ÉÍ¥½¸€ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°™™ÁÉ½‰”€µÙ•ÉÍ¥½¸É•ÑÕÉ¹•ÍÕ•ÍÌ‰ÕĞ‘¥¹½Ğ¥‘•¹Ñ¥™äÁÉ½‰”¸ˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°™™ÁÉ½‰”€µÙ•ÉÍ¥½¸½µÁ±•Ñ•ÍÕ•ÍÍ™Õ±±ä¸ˆ((€€€€‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€ô%¹Ù½­”µ¡•­•‘9…Ñ¥Ù”€µá•ÕÑ…‰±”€‘™µÁ•A…Ñ €µÉÕµ•¹ÑÌ  ˆµ‰Õ¥±‘½¹˜ˆ¤€µ•ÍÉ¥ÁÑ¥½¸€ˆ‘1…‰•°™™µÁ•œ€µ‰Õ¥±‘½¹˜ˆ(€€€¥˜€ ‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€µµ…Ñ €ˆ ı¤¤ üéyñqÌ¤´µ•¹…‰±”µÁ° üõqÍğ¤ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°µÁ•œ‰Õ¥±½¹™¥ÕÉ…Ñ¥½¸½¹Ñ…¥¹Ì€´µ•¹…‰±”µÁ°¸I•™ÕÍ¥¹œÑ¼‰Õ¹‘±”„A0‰Õ¥±¸ˆ(€€€ô(€€€¥˜€ ‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€µµ…Ñ €ˆ ı¤¤ üéyñqÌ¤´µ•¹…‰±”µ¹½¹™É•” üõqÍğ¤ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°µÁ•œ‰Õ¥±½¹™¥ÕÉ…Ñ¥½¸½¹Ñ…¥¹Ì€´µ•¹…‰±”µ¹½¹™É•”¸I•™ÕÍ¥¹œÑ¼‰Õ¹‘±”„¹½¹™É•”‰Õ¥±¸ˆ(€€€ô(€€€¥˜€ ‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€µ¹½Ñµ…Ñ €ˆ ı´¥yqÌ¨´µ…É õààÙ|ØÑqÌ¨ˆ€µ½È(€€€€€€€€‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€µ¹½Ñµ…Ñ €ˆ ı´¥yqÌ¨´µÑ…É•Ğµ½Ìõµ¥¹ÜÌÉqÌ¨ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°µÁ•œ‰Õ¥±½¹™¥ÕÉ…Ñ¥½¸‘½•Ì¹½Ğ¥‘•¹Ñ¥™ä]¥¹‘½İÌààÙ|ØĞ€¡µ¥¹ÜÌÈ¤¸ˆ(€€€ô(€€€¥˜€ ‘	Õ¥±‘½¹™¥ÕÉ…Ñ¥½¸€µ¹½Ñµ…Ñ €ˆ ı´¥yqÌ¨´µ•¹…‰±”µÙ•ÉÍ¥½¸ÍqÌ¨ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°µÁ•œ‰Õ¥±½¹™¥ÕÉ…Ñ¥½¸‘¥™™•ÉÌ™É½´Ñ¡”•áÁ•Ñ•1A0´Ì¸Àµ½Èµ±…Ñ•ÈÉ•±•…Í”¸ˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°‰Õ¥±½¹™¥ÕÉ…Ñ¥½¸¥Ì]¥¹‘½İÌàØĞ…¹¡…Ì¹¼€´µ•¹…‰±”µÁ°½È€´µ•¹…‰±”µ¹½¹™É•”¸ˆ((€€€€‘1¥•¹Í•=ÕÑÁÕĞ€ô%¹Ù½­”µ¡•­•‘9…Ñ¥Ù”€µá•ÕÑ…‰±”€‘™µÁ•A…Ñ €µÉÕµ•¹ÑÌ  ˆµ0ˆ¤€µ•ÍÉ¥ÁÑ¥½¸€ˆ‘1…‰•°™™µÁ•œ€µ0ˆ(€€€¥˜€ ‘1¥•¹Í•=ÕÑÁÕĞ€µ¹½Ñµ…Ñ €ˆ ı¥Ì¥9T1•ÍÍ•È•¹•É…°AÕ‰±¥Œ1¥•¹Í”¸¨ı•¥Ñ¡•ÈÙ•ÉÍ¥½¹qÌ¬ÍqÌ­½˜Ñ¡”1¥•¹Í”ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°±¥•¹Í”‘¥¹½Ğµ…Ñ •áÁ•Ñ•€‘™µÁ•1¥•¹Í”¸I•™ÕÍ¥¹œÑ¼‰Õ¹‘±”¥Ğ¸ˆ(€€€ô(€€€¥˜€ ‘1¥•¹Í•=ÕÑÁÕĞ€µµ…Ñ €‰9T•¹•É…°AÕ‰±¥Œ1¥•¹Í”ˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°É•Á½ÉÑÌÑ¡”A0¥¹ÍÑ•…½˜•áÁ•Ñ•€‘™µÁ•1¥•¹Í”¸I•™ÕÍ¥¹œÑ¼‰Õ¹‘±”¥Ğ¸ˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°É•Á½ÉÑÌÑ¡”•áÁ•Ñ•€‘™µÁ•1¥•¹Í”±¥•¹Í”¸ˆ((€€€€‘¹½‘•É1¥ÍĞ€ô%¹Ù½­”µ¡•­•‘9…Ñ¥Ù”€µá•ÕÑ…‰±”€‘™µÁ•A…Ñ €µÉÕµ•¹ÑÌ  ˆµ¡¥‘•}‰…¹¹•Èˆ°€ˆµ•¹½‘•ÉÌˆ¤€µ•ÍÉ¥ÁÑ¥½¸€ˆ‘1…‰•°™™µÁ•œ€µ•¹½‘•ÉÌˆ(€€€¥˜€ ‘¹½‘•É1¥ÍĞ€µ¹½Ñµ…Ñ €ˆ ı´¥yqÌ©YqL©qÌ­µÁ•œÑqÌˆ¤ì(€€€€€€€Ñ¡É½Ü€ˆ‘1…‰•°µÁ•œ‰Õ¥±¡…Ì¹¼5@ĞµÁ•œĞÙ¥‘•¼•¹½‘•È¸ˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t€‘1…‰•°µÁ•œĞÙ¥‘•¼•¹½‘•È¥Ì…Ù…¥±…‰±”¸ˆ)ô()¥˜€ µ¹½Ğ€¡•Ğµ½µµ…¹€‘AåÑ¡½¸€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”¤¤ìÑ¡É½Ü€‰AåÑ¡½¸±…Õ¹¡•È€œ‘AåÑ¡½¸œİ…Ì¹½Ğ™½Õ¹¸ˆô(‘AåÑ¡½¹ÉÌ€ô  ¤)¥˜€¡mMåÍÑ•´¹%<¹A…Ñ¡tèé•Ñ¥±•9…µ•]¥Ñ¡½ÕÑáÑ•¹Í¥½¸ ‘AåÑ¡½¸¤€µ•Ä€‰Áäˆ¤ì€‘AåÑ¡½¹ÉÌ€ô  ˆ´Ì¸ÄÄˆ¤ô(˜€‘AåÑ¡½¸AåÑ¡½¹ÉÌ€µŒ€‰¥µÁ½ÉĞÍåÌì…ÍÍ•ÉĞÍåÌ¹Ù•ÉÍ¥½¹}¥¹™½lèÉt€ôô€ Ì°ÄÄ¤°ÍåÌ¹Ù•ÉÍ¥½¸ˆ)¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰AåÑ¡½¸€Ì¸ÄÄ¥ÌÉ•ÅÕ¥É•¸ˆô)¥˜€ µ¹½Ğ€‘M­¥Á±•…¸¤ìI•µ½Ù”µ%Ñ•´€µI•ÕÉÍ”€µ½É”€¹‰Õ¥±µÑ•µÀ°‘¥ÍĞ€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”ô)9•Üµ%Ñ•´€µ%Ñ•µQåÁ”¥É•Ñ½Éä€µ½É”Ñ½½±Ìğ=ÕĞµ9Õ±°((‘™µÁ•i¥À€ô)½¥¸µA…Ñ €‘•¹ØéQ5@€‰±¥Á™½É”µ™™µÁ•œµ±Á°µİ¥¸ØĞ¹é¥Àˆ(‘™µÁ•½İ¹±½…€ô€ˆ‘™µÁ•i¥À¹‘½İ¹±½…ˆ)]É¥Ñ”µ!½ÍĞ€‰½İ¹±½…‘¥¹œÁ¥¹¹•]¥¹‘½İÌàØĞ1A0µÁ•œÉ•±•…Í”€‘™µÁ•I•±•…Í•Q…œ¸¸¸ˆ)I•µ½Ù”µ%Ñ•´€µ1¥Ñ•É…±A…Ñ €‘™µÁ•½İ¹±½…€µ½É”€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”)ÑÉäì(€€€%¹Ù½­”µ]•‰I•ÅÕ•ÍĞ€µUÉ¤€‘™µÁ•UÉ°€µ=ÕÑ¥±”€‘™µÁ•½İ¹±½…€µQ¥µ•½ÕÑM•Œ€ÄàÀ€µÉÉ½ÉÑ¥½¸MÑ½À)ô…Ñ ì(€€€€‘½İ¹±½…‘ÉÉ½È€ô€‘|¹á•ÁÑ¥½¸¹5•ÍÍ…”(€€€I•µ½Ù”µ%Ñ•´€µ1¥Ñ•É…±A…Ñ €‘™µÁ•½İ¹±½…€µ½É”€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”(€€€¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘™µÁ•i¥À€µA…Ñ¡QåÁ”1•…˜¤¤ì(€€€€€€€Ñ¡É½Ü€‰½Õ±¹½Ğ‘½İ¹±½…µÁ•œ…É¡¥Ù”€œ‘™µÁ•É¡¥Ù•9…µ”œ™É½´€‘™µÁ•UÉ°…¹¹¼Ù•É¥™¥•…¡•½Áä•á¥ÍÑÌ¸€‘½İ¹±½…‘ÉÉ½Èˆ(€€€ô(€€€€‘…¡•‘M¡„ÈÔØ€ô€¡•Ğµ¥±•!…Í €µ1¥Ñ•É…±A…Ñ €‘™µÁ•i¥À€µ±½É¥Ñ¡´M!ÈÔØ¤¹!…Í ¹Q½1½İ•É%¹Ù…É¥…¹Ğ ¤(€€€¥˜€ ‘…¡•‘M¡„ÈÔØ€µ¹”€‘™µÁ•M¡„ÈÔØ¤ì(€€€€€€€Ñ¡É½Ü€‰µÁ•œ‘½İ¹±½…™…¥±•…¹Ñ¡”…¡•…É¡¥Ù”M!´ÈÔØ¥Ì¥¹Ù…±¥¸áÁ•Ñ•€‘™µÁ•M¡„ÈÔØì½Ğ€‘…¡•‘M¡„ÈÔØ¸€‘½İ¹±½…‘ÉÉ½Èˆ(€€€ô(€€€]É¥Ñ”µ]…É¹¥¹œ€‰µÁ•œ‘½İ¹±½…™…¥±•ìÕÍ¥¹œÑ¡”…¡•…É¡¥Ù”…™Ñ•È¥ÑÌÁ¥¹¹•M!´ÈÔØİ…ÌÙ•É¥™¥•¸ˆ)ô)¥˜€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘™µÁ•½İ¹±½…€µA…Ñ¡QåÁ”1•…˜¤ì(€€€5½Ù”µ%Ñ•´€µ1¥Ñ•É…±A…Ñ €‘™µÁ•½İ¹±½…€µ•ÍÑ¥¹…Ñ¥½¸€‘™µÁ•i¥À€µ½É”)ô)¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘™µÁ•i¥À€µA…Ñ¡QåÁ”1•…˜¤¤ì(€€€Ñ¡É½Ü€‰µÁ•œ‘½İ¹±½…‘¥¹½ĞÉ•…Ñ”Ñ¡”•áÁ•Ñ•…É¡¥Ù”è€‘™µÁ•i¥Àˆ)ô(‘ÑÕ…±M¡„ÈÔØ€ô€¡•Ğµ¥±•!…Í €µ1¥Ñ•É…±A…Ñ €‘™µÁ•i¥À€µ±½É¥Ñ¡´M!ÈÔØ¤¹!…Í ¹Q½1½İ•É%¹Ù…É¥…¹Ğ ¤)¥˜€ ‘ÑÕ…±M¡„ÈÔØ€µ¹”€‘™µÁ•M¡„ÈÔØ¤ì(€€€Ñ¡É½Ü€‰µÁ•œ…É¡¥Ù”M!´ÈÔØµ¥Íµ…Ñ ¸áÁ•Ñ•€‘™µÁ•M¡„ÈÔØì½Ğ€‘ÑÕ…±M¡„ÈÔØ¸I•™ÕÍ¥¹œÑ¼•áÑÉ…Ğ¥Ğ¸ˆ)ô)]É¥Ñ”µ!½ÍĞ€‰m=-tµÁ•œ…É¡¥Ù”M!´ÈÔØÙ•É¥™¥•è€‘ÑÕ…±M¡„ÈÔØˆ((‘áÑÉ…Ğ€ô)½¥¸µA…Ñ €‘•¹ØéQ5@€‰±¥Á™½É”µ™™µÁ•œ´‘™µÁ•I•±•…Í•Q…œˆ)I•µ½Ù”µ%Ñ•´€µI•ÕÉÍ”€µ½É”€‘áÑÉ…Ğ€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”)ÑÉäì(€€€áÁ…¹µÉ¡¥Ù”€µA…Ñ €‘™µÁ•i¥À€µ•ÍÑ¥¹…Ñ¥½¹A…Ñ €‘áÑÉ…Ğ€µ½É”€µÉÉ½ÉÑ¥½¸MÑ½À)ô…Ñ ì(€€€Ñ¡É½Ü€‰½Õ±¹½Ğ•áÑÉ…ĞÑ¡”Ù•É¥™¥•µÁ•œ…É¡¥Ù”€œ‘™µÁ•É¡¥Ù•9…µ”œ¸€ ‘|¹á•ÁÑ¥½¸¹5•ÍÍ…”¤ˆ)ô(‘™µÁ•5…Ñ¡•Ì€ô ¡•Ğµ¡¥±‘%Ñ•´€‘áÑÉ…Ğ€µ¥±Ñ•È™™µÁ•œ¹•á”€µ¥±”€µI•ÕÉÍ”¤(‘™ÁÉ½‰•5…Ñ¡•Ì€ô ¡•Ğµ¡¥±‘%Ñ•´€‘áÑÉ…Ğ€µ¥±Ñ•È™™ÁÉ½‰”¹•á”€µ¥±”€µI•ÕÉÍ”¤)¥˜€ ‘™µÁ•5…Ñ¡•Ì¹½Õ¹Ğ€µ¹”€Ä¤ìÑ¡É½Ü€‰µÁ•œ…É¡¥Ù”µÕÍĞ½¹Ñ…¥¸•á…Ñ±ä½¹”™™µÁ•œ¹•á”ì™½Õ¹€ ‘™µÁ•5…Ñ¡•Ì¹½Õ¹Ğ¤¸ˆô)¥˜€ ‘™ÁÉ½‰•5…Ñ¡•Ì¹½Õ¹Ğ€µ¹”€Ä¤ìÑ¡É½Ü€‰µÁ•œ…É¡¥Ù”µÕÍĞ½¹Ñ…¥¸•á…Ñ±ä½¹”™™ÁÉ½‰”¹•á”ì™½Õ¹€ ‘™ÁÉ½‰•5…Ñ¡•Ì¹½Õ¹Ğ¤¸ˆô(‘±±5…Ñ¡•Ì€ô ¡•Ğµ¡¥±‘%Ñ•´€‘áÑÉ…Ğ€µ¥±Ñ•È€¨¹‘±°€µ¥±”€µI•ÕÉÍ”¤)¥˜€ ‘±±5…Ñ¡•Ì¹½Õ¹Ğ€µ•Ä€À¤ìÑ¡É½Ü€‰Q¡”Í•±•Ñ•µÁ•œÍ¡…É•…É¡¥Ù”½¹Ñ…¥¹Ì¹¼11ÌìÉ•™ÕÍ¥¹œ…¸¥¹½µÁ±•Ñ”‰Õ¹‘±”¸ˆô((ŒÑ½½±Ì¼¥ÌÉ•Í•ÉÙ•™½È‰Õ¹‘±•µÁ•œ™¥±•Ì¸I•µ½Ù”ÍÑ…±”11Ì…¹½±±¥•¹Í”(Œ™¥±•Ì™¥ÉÍĞÍ¼„ÁÉ•Ù¥½ÕÌ‰Õ¥±…¹¹½Ğ±•…Ù”Õ¹É•±…Ñ•‰¥¹…É¥•Ì¥¸Aå%¹ÍÑ…±±•È¸)•Ğµ¡¥±‘%Ñ•´Ñ½½±Ì€µ¥±”ğ]¡•É”µ=‰©•Ğì(€€€€‘|¹áÑ•¹Í¥½¸€µ¥•Ä€ˆ¹‘±°ˆ€µ½È(€€€€‘|¹9…µ”€µµ…Ñ €‰x¡™™µÁ•ñ™™ÁÉ½‰”¥p¹•á”‘ñy=Ae%9p¹1A1ÙlÈÍt üép¸Ä¤üˆ)ôğI•µ½Ù”µ%Ñ•´€µ½É”)½Áäµ%Ñ•´€‘™µÁ•5…Ñ¡•ÍlÁt¹Õ±±9…µ”€¡)½¥¸µA…Ñ €‘I½½Ğ€‰Ñ½½±Íq™™µÁ•œ¹•á”ˆ¤€µ½É”)½Áäµ%Ñ•´€‘™ÁÉ½‰•5…Ñ¡•ÍlÁt¹Õ±±9…µ”€¡)½¥¸µA…Ñ €‘I½½Ğ€‰Ñ½½±Íq™™ÁÉ½‰”¹•á”ˆ¤€µ½É”)™½É•… € ‘±°¥¸€‘±±5…Ñ¡•Ì¤ì(€€€½Áäµ%Ñ•´€‘±°¹Õ±±9…µ”€¡)½¥¸µA…Ñ €‘I½½Ğ€ ‰Ñ½½±Ípˆ€¬€‘±°¹9…µ”¤¤€µ½É”)ô((ŒY…±¥‘…Ñ”Ñ¡”•á…Ğ‘¥É•Ñ½ÉäÑ¡…ĞAå%¹ÍÑ…±±•Èİ¥±°½±±•Ğ°¥¹±Õ‘¥¹œ…±°(ŒÍ¡…É•11ÌÉ•ÅÕ¥É•Ñ¼±…Õ¹ Ñ¡”•á•ÕÑ…‰±•Ì¸)ÍÍ•ÉĞµ™µÁ•	Õ¹‘±”€µ¥É•Ñ½Éä€¡)½¥¸µA…Ñ €‘I½½Ğ€‰Ñ½½±Ìˆ¤€µ1…‰•°€‰MÑ…•µÁ•œ‰Õ¹‘±”ˆ((‘1¥•¹Í•A…Ñ €ô)½¥¸µA…Ñ €‘I½½Ğ€‰Ñ½½±Íq=Ae%9¹1A1ØÌˆ(‘1¥•¹Í•M½ÕÉ•A…Ñ €ô)½¥¸µA…Ñ €‘I½½Ğ€‰±¥•¹Í•Íq=Ae%9¹1A1ØÌˆ)¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘1¥•¹Í•M½ÕÉ•A…Ñ €µA…Ñ¡QåÁ”1•…˜¤¤ì(€€€Ñ¡É½Ü€‰Q¡”¡•­•µ¥¸1A0ØÌ±¥•¹Í”Ñ•áĞ¥Ìµ¥ÍÍ¥¹œè€‘1¥•¹Í•M½ÕÉ•A…Ñ ˆ)ô(‘1¥•¹Í•Q•áÑM¡„ÈÔØ€ô€¡•Ğµ¥±•!…Í €µ1¥Ñ•É…±A…Ñ €‘1¥•¹Í•M½ÕÉ•A…Ñ €µ±½É¥Ñ¡´M!ÈÔØ¤¹!…Í ¹Q½1½İ•É%¹Ù…É¥…¹Ğ ¤)¥˜€ ‘1¥•¹Í•Q•áÑM¡„ÈÔØ€µ¹”€‘™µÁ•1¥•¹Í•Q•áÑM¡„ÈÔØ¤ì(€€€Ñ¡É½Ü€‰1A0±¥•¹Í”Ñ•áĞM!´ÈÔØµ¥Íµ…Ñ ¸áÁ•Ñ•€‘™µÁ•1¥•¹Í•Q•áÑM¡„ÈÔØì½Ğ€‘1¥•¹Í•Q•áÑM¡„ÈÔØ¸ˆ)ô)½Áäµ%Ñ•´€µ1¥Ñ•É…±A…Ñ €‘1¥•¹Í•M½ÕÉ•A…Ñ €µ•ÍÑ¥¹…Ñ¥½¸€‘1¥•¹Í•A…Ñ €µ½É”)]É¥Ñ”µ!½ÍĞ€‰m=-t=™™¥¥…°1A0ØÌ±¥•¹Í”Ñ•áĞM!´ÈÔØÙ•É¥™¥•è€‘1¥•¹Í•Q•áÑM¡„ÈÔØˆ()M•Ğµ½¹Ñ•¹Ğ€µA…Ñ €¡)½¥¸µA…Ñ €‘I½½Ğ€‰Q!%I}AIQe}9=Q%L¹ÑáĞˆ¤€µY…±Õ” ˆ)±¥Á½É”$Ñ¡¥ÉµÁ…ÉÑä½µÁ½¹•¹ÑÌ()µÁ•œè€‘™µÁ•1¥•¹Í”°]¥¹‘½İÌàØĞÍ¡…É•‰Õ¥±¸)É¡¥Ù”è€‘™µÁ•É¡¥Ù•9…µ”)É¡¥Ù”M!´ÈÔØè€‘™µÁ•M¡„ÈÔØ)I•±•…Í”è¡ÑÑÁÌè¼½¥Ñ¡Õˆ¹½´½µÁ•œµ	Õ¥±‘Ì½µÁ•œµ	Õ¥±‘Ì½É•±•…Í•Ì½Ñ…œ¼‘™µÁ•I•±•…Í•Q…œ)1¥•¹Í”Ñ•áĞèÑ½½±Íq=Ae%9¹1A1ØÌ€ ‘™µÁ•1¥•¹Í•UÉ°¤)µÁ•œÍ½ÕÉ”è¡ÑÑÁÌè¼½™™µÁ•œ¹½Éœ¼)M¡…É•µÁ•œ11Ì…É”‰Õ¹‘±•Ñ¼ÍÕÁÁ½ÉĞÉ•Á±…•µ•¹ĞÕ¹‘•È1A0Ñ•ÉµÌ¸()AåM¥‘”Ø€¼EĞ°™…ÍÑ•Èµİ¡¥ÍÁ•È°QÉ…¹Í±…Ñ”È…¹AåX…É”Ñ¡¥ÉµÁ…ÉÑä½µÁ½¹•¹ÑÌ)Õ¹‘•ÈÑ¡•¥ÈÉ•ÍÁ•Ñ¥Ù”±¥•¹Í•Ì¸½¹ÍÕ±ĞÕÁÍÑÉ•…´±¥•¹Í”™¥±•Ì¸(‰ €µ¹½‘¥¹œUQà((˜€‘AåÑ¡½¸AåÑ¡½¹ÉÌ€µ´Ù•¹Ø€¹Ù•¹Øµ‰Õ¥±)¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰½Õ±¹½ĞÉ•…Ñ”€¹Ù•¹Øµ‰Õ¥±İ¥Ñ AåÑ¡½¸€Ì¸ÄÄ¸ˆô(‘Y•¹ÙAåÑ¡½¸€ô)½¥¸µA…Ñ €‘I½½Ğ€ˆ¹Ù•¹Øµ‰Õ¥±‘qMÉ¥ÁÑÍqÁåÑ¡½¸¹•á”ˆ)¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘Y•¹ÙAåÑ¡½¸€µA…Ñ¡QåÁ”1•…˜¤¤ìÑ¡É½Ü€‰Y¥ÉÑÕ…°•¹Ù¥É½¹µ•¹ĞAåÑ¡½¸•á•ÕÑ…‰±”İ…Ì¹½ĞÉ•…Ñ•è€‘Y•¹ÙAåÑ¡½¸ˆô(˜€‘Y•¹ÙAåÑ¡½¸€µ´Á¥À¥¹ÍÑ…±°€´µÕÁÉ…‘”Á¥À)¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰	Õ¥±‘•Á•¹‘•¹ä‰½½ÑÍÑÉ…À™…¥±•İ¡¥±”ÕÁÉ…‘¥¹œÁ¥À¸ˆô(˜€‘Y•¹ÙAåÑ¡½¸€µ´Á¥À¥¹ÍÑ…±°€µÈÉ•ÅÕ¥É•µ•¹ÑÌµ‰Õ¥±¹ÑáĞ)¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰	Õ¥±‘•Á•¹‘•¹ä¥¹ÍÑ…±±…Ñ¥½¸™…¥±•¸ˆô(‘•¹ØéAQ €ô€ˆ¡)½¥¸µA…Ñ €‘I½½Ğ€Ñ½½±Ìœ¤ì‘•¹ØéAQ ˆ(˜€‘Y•¹ÙAåÑ¡½¸‰Õ¥±‘q¡•­}‘•Á•¹‘•¹¥•Ì¹Áä)¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰•Á•¹‘•¹ä¡•¬™…¥±•¸ˆô((Œ-••ÀÕ¹É•±…Ñ•¡½ÍĞ10‘¥É•Ñ½É¥•Ì€¡™½È•á…µÁ±”°„‰Õ¹‘±•A½ÁÁ±•È½%T¥¸(ŒÑ¡”½‘•àÉÕ¹Ñ¥µ”AQ ¤½ÕĞ½˜Aå%¹ÍÑ…±±•ÈÌ‘•Á•¹‘•¹äÉ•Í½±ÕÑ¥½¸¸µÁ•œ¥Ì(ŒÍÑ…•¥¸Ñ½½±ÌìÑ¡”É•µ…¥¹¥¹œ¹…Ñ¥Ù”‘•Á•¹‘•¹¥•Ì…É”½±±•Ñ•™É½´Ñ¡”(Œ‰Õ¥±Ù•¹Ø½ÈÉ•Í½±Ù•™É½´]¥¹‘½İÌÍåÍÑ•´‘¥É•Ñ½É¥•Ì¸(‘A…Ñ¡	•™½É•Aå%¹ÍÑ…±±•È€ô€‘•¹ØéAQ (‘Aå%¹ÍÑ…±±•ÉA…Ñ €ô  (€€€€¡)½¥¸µA…Ñ €‘I½½Ğ€‰Ñ½½±Ìˆ¤(€€€€¡)½¥¸µA…Ñ €‘I½½Ğ€ˆ¹Ù•¹Øµ‰Õ¥±‘qMÉ¥ÁÑÌˆ¤(€€€€¡)½¥¸µA…Ñ €‘•¹ØéMåÍÑ•µI½½Ğ€‰MåÍÑ•´ÌÈˆ¤(€€€€‘•¹ØéMåÍÑ•µI½½Ğ(¤ğM•±•Ğµ=‰©•Ğ€µU¹¥ÅÕ”(‘•¹ØéAQ €ô€‘Aå%¹ÍÑ…±±•ÉA…Ñ €µ©½¥¸mMåÍÑ•´¹%<¹A…Ñ¡tèéA…Ñ¡M•Á…É…Ñ½È)ÑÉäì(€€€€˜€‘Y•¹ÙAåÑ¡½¸€µ´Aå%¹ÍÑ…±±•È€´µ¹½½¹™¥É´€´µ±•…¸€´µİ½É­Á…Ñ €¹‰Õ¥±µÑ•µÀ±¥Á™½É”¹ÍÁ•Œ(€€€€‘Aå%¹ÍÑ…±±•Éá¥Ñ½‘”€ô€‘1MQa%Q=)ô™¥¹…±±äì(€€€€‘•¹ØéAQ €ô€‘A…Ñ¡	•™½É•Aå%¹ÍÑ…±±•È)ô)¥˜€ ‘Aå%¹ÍÑ…±±•Éá¥Ñ½‘”€µ¹”€À¤ìÑ¡É½Ü€‰Aå%¹ÍÑ…±±•È™…¥±•¸ˆô((‘A½ÉÑ…‰±•¥É•Ñ½Éä€ô)½¥¸µA…Ñ €‘I½½Ğ€‰‘¥ÍÑq±¥Á½É•$ˆ(‘U¹•áÁ•Ñ•‘%Õ±±Ì€ô ¡•Ğµ¡¥±‘%Ñ•´€µ1¥Ñ•É…±A…Ñ €‘A½ÉÑ…‰±•¥É•Ñ½Éä€µ¥±Ñ•È€‰¥Ô¨¹‘±°ˆ€µ¥±”€µI•ÕÉÍ”¤)¥˜€ ‘U¹•áÁ•Ñ•‘%Õ±±Ì¹½Õ¹Ğ€µĞ€À¤ì(€€€€‘U¹•áÁ•Ñ•‘9…µ•Ì€ô€ ‘U¹•áÁ•Ñ•‘%Õ±±Ìğ½É… µ=‰©•Ğì€‘|¹Õ±±9…µ”ô¤€µ©½¥¸€ˆ°€ˆ(€€€Ñ¡É½Ü€‰Aå%¹ÍÑ…±±•È‰Õ¹‘±•%T11Ì™É½´Ñ¡”‰Õ¥±¡½ÍĞ¸Q¡•Í”…¸Í¡…‘½ÜÑ¡”]¥¹‘½İÌ%TÉ•ÅÕ¥É•‰äEĞè€‘U¹•áÁ•Ñ•‘9…µ•Ìˆ)ô(‘A…­…•‘Q½½±Í¥É•Ñ½Éä€ô)½¥¸µA…Ñ €‘A½ÉÑ…‰±•¥É•Ñ½Éä€‰}¥¹Ñ•É¹…±qÑ½½±Ìˆ)¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘A…­…•‘Q½½±Í¥É•Ñ½Éä€µA…Ñ¡QåÁ”½¹Ñ…¥¹•È¤¤ì(€€€€ŒAå%¹ÍÑ…±±•È€Ø¸ÄÈ¬ÍÑ½É•Ì½¹”µ™½±‘•ÈÁ…å±½…™¥±•Ì¥¸}¥¹Ñ•É¹…°¸=±‘•È€Ø¹à(€€€€ŒÉ•±•…Í•ÌÁ±…”Ñ¡•´‰•Í¥‘”Ñ¡”•á•ÕÑ…‰±”ì‰½Ñ ±…å½ÕÑÌµ…Ñ ÍåÌ¹}5%AML¸(€€€€‘A…­…•‘Q½½±Í¥É•Ñ½Éä€ô)½¥¸µA…Ñ €‘A½ÉÑ…‰±•¥É•Ñ½Éä€‰Ñ½½±Ìˆ)ô)™½É•… € ‘I•ÅÕ¥É•‘¥±”¥¸  ‰™™µÁ•œ¹•á”ˆ°€‰™™ÁÉ½‰”¹•á”ˆ°€‰=Ae%9¹1A1ØÌˆ¤¤ì(€€€€‘A…­…•‘A…Ñ €ô)½¥¸µA…Ñ €‘A…­…•‘Q½½±Í¥É•Ñ½Éä€‘I•ÅÕ¥É•‘¥±”(€€€¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘A…­…•‘A…Ñ €µA…Ñ¡QåÁ”1•…˜¤¤ì(€€€€€€€Ñ¡É½Ü€‰Aå%¹ÍÑ…±±•ÈÁ½ÉÑ…‰±”‰Õ¥±¥Ìµ¥ÍÍ¥¹œÉ•ÅÕ¥É•µÁ•œ™¥±”è€‘A…­…•‘A…Ñ ˆ(€€€ô)ô)ÍÍ•ÉĞµ™µÁ•	Õ¹‘±”€µ¥É•Ñ½Éä€‘A…­…•‘Q½½±Í¥É•Ñ½Éä€µ1…‰•°€‰Aå%¹ÍÑ…±±•ÈÁ½ÉÑ…‰±”‰Õ¹‘±”ˆ)½Áäµ%Ñ•´I5¹µ°%}5=1L¹µ°Q!%I}AIQe}9=Q%L¹ÑáĞ°%9MQ11}$¹‰…Ğ€µ•ÍÑ¥¹…Ñ¥½¸€‘A½ÉÑ…‰±•¥É•Ñ½Éä€µ½É”)]É¥Ñ”µ!½ÍĞ€‰A½ÉÑ…‰±”™½±‘•ÈÉ•…Ñ•è‘¥ÍÑq±¥Á½É•$ˆ€µ½É•É½Õ¹‘½±½ÈÉ••¸((‘%Í½µµ…¹€ô•Ğµ½µµ…¹%M¹•á”€µÉÉ½ÉÑ¥½¸M¥±•¹Ñ±å½¹Ñ¥¹Õ”(‘%ÍA…Ñ €ô¥˜€ ‘%Í½µµ…¹¤ì€‘%Í½µµ…¹¹M½ÕÉ”ô•±Í”ì€‘¹Õ±°ô)¥˜€ µ¹½Ğ€‘%ÍA…Ñ ¤ì(€€€€‘…¹‘¥‘…Ñ”€ô€ˆ‘•¹ØéAÉ½É…µ¥±•Ì¡ààØ¥q%¹¹¼M•ÑÕÀ€Ùq%M¹•á”ˆ(€€€¥˜€¡Q•ÍĞµA…Ñ €‘…¹‘¥‘…Ñ”¤ì€‘%ÍA…Ñ €ô€‘…¹‘¥‘…Ñ”ô)ô)¥˜€ ‘%ÍA…Ñ ¤ì(€€€9•Üµ%Ñ•´€µ%Ñ•µQåÁ”¥É•Ñ½Éä€µ½É”‘¥ÍÑq¥¹ÍÑ…±±•Èğ=ÕĞµ9Õ±°(€€€€˜€‘%ÍA…Ñ ¥¹ÍÑ…±±•Éq±¥Á½É•$¹¥ÍÌ(€€€¥˜€ ‘1MQa%Q=€µ¹”€À¤ìÑ¡É½Ü€‰%¹¹¼M•ÑÕÀ½µÁ¥±…Ñ¥½¸™…¥±•¸ˆô(€€€€‘%¹ÍÑ…±±•È€ô)½¥¸µA…Ñ €‘I½½Ğ€‰‘¥ÍÑq¥¹ÍÑ…±±•Éq±¥Á½É•$µM•ÑÕÀ´À¸Ì¸ÀµàØĞ¹•á”ˆ(€€€¥˜€ µ¹½Ğ€¡Q•ÍĞµA…Ñ €µ1¥Ñ•É…±A…Ñ €‘%¹ÍÑ…±±•È€µA…Ñ¡QåÁ”1•…˜¤€µ½È€¡•Ğµ%Ñ•´€‘%¹ÍÑ…±±•È¤¹1•¹Ñ €µ•Ä€À¤ì(€€€€€€€Ñ¡É½Ü€‰%¹¹¼M•ÑÕÀÉ•Á½ÉÑ•ÍÕ•ÍÌ‰ÕĞ‘¥¹½ĞÉ•…Ñ”Ñ¡”•áÁ•Ñ•¥¹ÍÑ…±±•Èè€‘%¹ÍÑ…±±•Èˆ(€€€ô(€€€]É¥Ñ”µ!½ÍĞ€‰m=-t%¹¹¼M•ÑÕÀ¥¹ÍÑ…±±•ÈÉ•…Ñ•è‘¥ÍÑq¥¹ÍÑ…±±•Éq±¥Á½É•$µM•ÑÕÀ´À¸Ì¸ÀµàØĞ¹•á”ˆ)ô•±Í”ì]É¥Ñ”µ]…É¹¥¹œ€‰%¹¹¼M•ÑÕÀ€Ø¹½Ğ™½Õ¹ì¥¹ÍÑ…±±•ÈÍ­¥ÁÁ•¸ˆô