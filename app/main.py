from __future__ import annotations
import json, os, re, shutil, subprocess, sys, uuid
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QFont, QFontMetrics, QColor, QDesktopServices, QImage, QPainter, QRect
from ai_engine import run_analysis
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QFrame, QLineEdit,
    QDoubleSpinBox, QComboBox, QProgressBar, QMessageBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit, QAbstractItemView, QCheckBox
)

APP_NAME = "ClipForge AI"


def prepare_workspace() -> tuple[Path, Path, Path]:
    preferred = Path.home() / "Videos" / "ClipForge AI"
    local_app_data = os.environ.get("LOCALAPPDATA")
    fallback_base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    errors = []

    for root in (preferred, fallback_base / "ClipForge AI"):
        projects = root / "Projects"
        exports = root / "Exports"
        try:
            projects.mkdir(parents=True, exist_ok=True)
            exports.mkdir(parents=True, exist_ok=True)
            return root, projects, exports
        except OSError as exc:
            errors.append(f"{root}: {exc}")

    details = "\n".join(errors)
    raise RuntimeError(f"Не удалось создать рабочие папки ClipForge AI. Проверь права доступа.\n{details}")


ROOT, PROJECTS, EXPORTS = prepare_workspace()


def youtube_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        raise ValueError("Поддерживаются HTTPS-ссылки YouTube: youtube.com и youtu.be.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("В ссылке указан некорректный порт.") from exc
    if port not in (None, 443) or parsed.username or parsed.password:
        raise ValueError("Используй обычную HTTPS-ссылку YouTube без учётных данных и нестандартного порта.")

    parts = [part for part in parsed.path.split("/") if part]
    video_id = None
    if host == "youtu.be":
        video_id = parts[0] if parts else None
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
        video_id = parts[1]

    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Не удалось распознать ID YouTube-видео в этой ссылке.")
    return video_id


def create_commentary_overlay(text: str, ratio: str, output_path: Path) -> None:
    dimensions = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
    width, height = dimensions[ratio]
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    padding = max(28, int(min(width, height) * 0.04))
    inner_width = width - padding * 4
    header_font = QFont("Segoe UI", max(17, int(min(width, height) * 0.023)), QFont.DemiBold)
    body_font = QFont("Segoe UI", max(26, int(min(width, height) * 0.038)), QFont.DemiBold)
    header_height = max(28, int(min(width, height) * 0.035))
    line_gap = max(8, int(min(width, height) * 0.012))
    text_area = QRect(0, 0, inner_width, int(height * 0.28))
    text_bounds = QFontMetrics(body_font).boundingRect(text_area, Qt.TextWordWrap, text)
    body_height = min(max(text_bounds.height(), body_font.pixelSize()), int(height * 0.28))
    panel_height = padding * 2 + header_height + line_gap + body_height
    panel = QRect(padding, padding, width - padding * 2, panel_height)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(17, 19, 24, 220))
    painter.drawRoundedRect(panel, max(16, padding // 2), max(16, padding // 2))
    painter.setPen(QColor(178, 165, 255))
    painter.setFont(header_font)
    painter.drawText(QRect(panel.x() + padding, panel.y() + padding // 2, inner_width, header_height), Qt.AlignLeft | Qt.AlignVCenter, "МОЙ КОММЕНТАРИЙ")
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(body_font)
    body_rect = QRect(panel.x() + padding, panel.y() + padding // 2 + header_height + line_gap, inner_width, body_height)
    painter.drawText(body_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, text)
    painter.end()

    if not image.save(str(output_path), "PNG"):
        raise RuntimeError("Не удалось подготовить видимый слой комментария для клипа.")


def find_bin(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    local = bundle_root / "tools" / exe
    if local.exists(): return str(local)
    return shutil.which(exe)


def probe_video(path: str) -> dict:
    ffprobe = find_bin("ffprobe")
    if not ffprobe: raise RuntimeError("Не найден ffprobe. Установи FFmpeg и добавь папку bin в PATH.")
    p = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "Не удалось прочитать видео")
    data = json.loads(p.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration": float(data.get("format", {}).get("duration", 0)), "width": video.get("width", 0), "height": video.get("height", 0), "fps": video.get("r_frame_rate", "—"), "codec": video.get("codec_name", "—")}


class RenderWorker(QThread):
    done = Signal(str)
    failed = Signal(str)
    progress = Signal(int)
    def __init__(self, source: str, start: float, end: float, output: str, ratio: str, overlay_path: str | None = None):
        super().__init__(); self.source=source; self.start_at=start; self.end_at=end; self.output=output; self.ratio=ratio; self.overlay_path=overlay_path
    def run(self):
        ffmpeg = find_bin("ffmpeg")
        if not ffmpeg: self.failed.emit("Не найден ffmpeg. Установи FFmpeg и добавь папку bin в PATH."); return
        if self.end_at <= self.start_at: self.failed.emit("Время окончания должно быть больше времени начала."); return
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
        if self.overlay_path:
            filter_complex=f"[0:v]{filt}[base];[1:v]format=rgba[commentary];[base][commentary]overlay=0:0:shortest=1:format=auto[v]"
            cmd=[ffmpeg,"-y","-ss",str(self.start_at),"-i",self.source,"-loop","1","-i",self.overlay_path,"-t",str(self.end_at-self.start_at),"-filter_complex",filter_complex,"-map","[v]","-map","0:a?","-shortest",*video_codec,"-c:a","aac","-b:a","192k","-movflags","+faststart",self.output]
        else:
            cmd=[ffmpeg,"-y","-ss",str(self.start_at),"-i",self.source,"-t",str(self.end_at-self.start_at),"-vf",filt,*video_codec,"-c:a","aac","-b:a","192k","-movflags","+faststart",self.output]
        p=subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode: self.failed.emit(p.stderr[-1800:] or "Ошибка FFmpeg")
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
        self.source_url=None; self.pending_export_metadata={}; self.pending_overlay_paths={}
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
        top=QHBoxLayout(); brand=QLabel("ClipForge AI"); brand.setObjectName("Brand"); top.addWidget(brand); top.addWidget(QLabel("LOCAL VIDEO STUDIO")); top.addStretch(); self.status=QLabel("Проверка компонентов…"); self.status.setObjectName("Muted"); top.addWidget(self.status); main.addLayout(top)
        intro=QLabel("Превращай длинные видео в вертикальные клипы — прямо на своём компьютере."); intro.setObjectName("Muted"); main.addWidget(intro)
        tabs=QTabWidget(); main.addWidget(tabs)
        home=QWidget(); h=QVBoxLayout(home); h.setContentsMargins(14,14,14,14); h.setSpacing(14)
        row=QHBoxLayout(); left, ll=self.panel(); ll.addWidget(QLabel("ИСХОДНОЕ ВИДЕО")); self.file_label=QLabel("Видео ещё не выбрано"); self.file_label.setWordWrap(True); self.file_label.setStyleSheet("font-size:14pt;font-weight:600"); ll.addWidget(self.file_label); self.meta=QLabel("Добавь видеофайл, чтобы увидеть его параметры."); self.meta.setObjectName("Muted"); self.meta.setWordWrap(True); ll.addWidget(self.meta); choose=QPushButton("＋  Добавить видео"); choose.setObjectName("Primary"); choose.clicked.connect(self.choose_video); ll.addWidget(choose); row.addWidget(left,2)
        right,rl=self.panel(); rl.addWidget(QLabel("БЫСТРОЕ ДЕЙСТВИЕ")); rl.addWidget(QLabel("Создать клип")); rl.addWidget(QLabel("Выбери начало и конец фрагмента, формат и нажми «Рендерить».")); self.start_spin=QDoubleSpinBox(); self.start_spin.setRange(0,999999); self.start_spin.setDecimals(2); self.start_spin.setSuffix(" сек — начало"); self.end_spin=QDoubleSpinBox(); self.end_spin.setRange(0,999999); self.end_spin.setDecimals(2); self.end_spin.setValue(30); self.end_spin.setSuffix(" сек — конец"); rl.addWidget(self.start_spin); rl.addWidget(self.end_spin); self.ratio=QComboBox(); self.ratio.addItems(["9:16 — YouTube Shorts / Reels / TikTok","1:1 — квадрат","16:9 — горизонтальное"]); rl.addWidget(self.ratio); self.render_btn=QPushButton("Рендерить клип"); self.render_btn.setObjectName("Primary"); self.render_btn.clicked.connect(self.render_clip); rl.addWidget(self.render_btn); self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); rl.addWidget(self.progress); row.addWidget(right,3); h.addLayout(row)
        bottom=QHBoxLayout(); exp,el=self.panel(); el.addWidget(QLabel("ПОСЛЕДНИЕ ЭКСПОРТЫ")); self.exports=QListWidget(); el.addWidget(self.exports); bottom.addWidget(exp,2); notes,nl=self.panel(); nl.addWidget(QLabel("СЛЕДУЮЩИЕ ВОЗМОЖНОСТИ")); nl.addWidget(QLabel("• AI-поиск лучших моментов\n• Автоматические субтитры\n• Пакетная нарезка\n• Шаблоны оформления\n• Ручная временная шкала")); nl.addStretch(); nl.addWidget(QLabel("Это стартовая локальная версия. AI-анализ и расширенный монтаж будут добавлены следующими этапами."),0); bottom.addWidget(notes,1); h.addLayout(bottom); tabs.addTab(home,"Обзор")
        library=QWidget(); lv=QVBoxLayout(library); lv.addWidget(QLabel("Файлы, которые ты экспортировал из ClipForge AI.")); self.export_table=QTableWidget(0,2); self.export_table.setHorizontalHeaderLabels(["Файл","Расположение"]); self.export_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.export_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch); lv.addWidget(self.export_table); open_folder=QPushButton("Открыть папку экспорта"); open_folder.clicked.connect(lambda: os.startfile(str(EXPORTS)) if os.name=="nt" else None); lv.addWidget(open_folder); tabs.addTab(library,"Экспорты")
        ai=QWidget(); av=QVBoxLayout(ai); av.setContentsMargins(14,14,14,14); av.setSpacing(12)
        ai_info, ail=self.panel(); ail.addWidget(QLabel("AI VIDEO ANALYZER")); ail.addWidget(QLabel("Локальная расшифровка речи и поиск самостоятельных фрагментов для Shorts. Сначала установи AI-компоненты через INSTALL_AI.bat.")); av.addWidget(ai_info)
        controls=QHBoxLayout(); self.whisper_choice=QComboBox(); self.whisper_choice.addItems(["small — быстрее, рекомендовано", "medium — точнее, медленнее", "large-v3-turbo — максимальное качество"])
        self.ai_run_btn=QPushButton("Анализировать текущее видео"); self.ai_run_btn.setObjectName("Primary"); self.ai_run_btn.clicked.connect(self.start_ai_analysis); controls.addWidget(self.whisper_choice,2); controls.addWidget(self.ai_run_btn,1); av.addLayout(controls)
        self.ai_progress=QProgressBar(); self.ai_progress.setRange(0,0); self.ai_progress.hide(); av.addWidget(self.ai_progress)
        self.ai_status=QLabel("Ожидание видео. Анализ выполняется локально."); self.ai_status.setObjectName("Muted"); av.addWidget(self.ai_status)
        self.ai_table=QTableWidget(0,5); self.ai_table.setHorizontalHeaderLabels(["Оценка","Название","Начало","Конец","Почему выбрано"]); self.ai_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.ai_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch); self.ai_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.ai_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.ai_table.cellDoubleClicked.connect(self.select_ai_clip); av.addWidget(self.ai_table)
        ai_actions=QHBoxLayout(); self.use_clip_btn=QPushButton("Использовать выбранный фрагмент"); self.use_clip_btn.clicked.connect(self.use_selected_ai_clip); ai_actions.addWidget(self.use_clip_btn); ai_actions.addStretch(); av.addLayout(ai_actions); av.addStretch(); tabs.addTab(ai,"AI Analyzer")
        source_tab=QWidget(); source_layout=QVBoxLayout(source_tab); source_layout.setContentsMargins(14,14,14,14); source_layout.setSpacing(12)
        source_panel, source_box=self.panel(); source_box.addWidget(QLabel("ССЫЛКА НА ИСХОДНИК")); source_box.addWidget(QLabel("Вставь HTTPS-ссылку на YouTube. Она сохранится рядом с экспортом как источник; видео с YouTube приложение не скачивает."))
        self.source_url_edit=QLineEdit(); self.source_url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…"); source_box.addWidget(self.source_url_edit)
        source_actions=QHBoxLayout(); self.attach_source_btn=QPushButton("Привязать источник"); self.attach_source_btn.clicked.connect(self.attach_source); source_actions.addWidget(self.attach_source_btn); self.open_source_btn=QPushButton("Открыть видео на YouTube"); self.open_source_btn.setEnabled(False); self.open_source_btn.clicked.connect(self.open_source); source_actions.addWidget(self.open_source_btn); source_actions.addStretch(); source_box.addLayout(source_actions)
        self.source_status=QLabel("Чтобы монтировать видео, добавь его файл на вкладке «Обзор». Используй файл, который ты создал или имеешь право обрабатывать."); self.source_status.setObjectName("Muted"); self.source_status.setWordWrap(True); source_box.addWidget(self.source_status)
        self.rights_confirmation=QCheckBox("Подтверждаю, что создал это видео или имею разрешение на его обработку"); source_box.addWidget(self.rights_confirmation); source_layout.addWidget(source_panel)
        commentary_panel, commentary_box=self.panel(); commentary_box.addWidget(QLabel("ВИДИМЫЙ АВТОРСКИЙ КОММЕНТАРИЙ")); commentary_box.addWidget(QLabel("Необязательный текст будет виден поверх клипа. Он также сохранится в метаданных экспорта."))
        self.commentary_edit=QTextEdit(); self.commentary_edit.setPlaceholderText("Добавь собственное пояснение или контекст к этому фрагменту…"); self.commentary_edit.setMaximumHeight(120); commentary_box.addWidget(self.commentary_edit)
        commentary_box.addWidget(QLabel("Текстовое оформление не заменяет разрешение на использование исходного видео.")); source_layout.addWidget(commentary_panel); source_layout.addStretch(); tabs.addTab(source_tab,"Источник и стиль")
        settings=QWidget(); sv=QVBoxLayout(settings); sv.addWidget(QLabel("Локальные настройки")); sv.addWidget(QLabel(f"Рабочая папка: {ROOT}")); sv.addWidget(QLabel("FFmpeg и FFprobe должны быть доступны через PATH или лежать в папке tools рядом с программой.")); sv.addStretch(); tabs.addTab(settings,"Настройки")
        foot=QLabel("CLIPFORGE AI  •  WINDOWS FULL BUILD  •  ALPHA 0.3.0"); foot.setObjectName("Muted"); main.addWidget(foot)

    def check_ffmpeg(self):
        ok=find_bin("ffmpeg") and find_bin("ffprobe")
        self.status.setText("● FFmpeg готов" if ok else "● Требуется FFmpeg")
        self.status.setStyleSheet("color:#66d9a3" if ok else "color:#ffbd69")

    def choose_video(self):
        path,_=QFileDialog.getOpenFileName(self,"Выбрать исходное видео","", "Видео (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;Все файлы (*.*)")
        if not path: return
        try: info=probe_video(path)
        except Exception as e: QMessageBox.critical(self,"Не удалось открыть видео",str(e)); return
        self.current_video=path; self.video_info=info; self.file_label.setText(Path(path).name)
        self.meta.setText(f"{info['width']} × {info['height']} px  •  {self.fmt(info['duration'])}  •  {info['codec']}  •  {Path(path).stat().st_size/1024/1024:.1f} MB")
        self.start_spin.setValue(0); self.end_spin.setValue(min(30,info['duration']))

    def attach_source(self):
        try:
            video_id=youtube_video_id(self.source_url_edit.text())
        except ValueError as exc:
            self.source_url=None; self.open_source_btn.setEnabled(False); self.source_status.setText(str(exc)); return
        self.source_url=f"https://www.youtube.com/watch?v={video_id}"
        self.source_url_edit.setText(self.source_url); self.open_source_btn.setEnabled(True)
        self.source_status.setText(f"Источник привязан: YouTube · {video_id}. Для монтажа отдельно выбери разрешённый видеофайл на вкладке «Обзор».")

    def open_source(self):
        try:
            video_id=youtube_video_id(self.source_url_edit.text())
        except ValueError as exc:
            QMessageBox.warning(self,"Ссылка YouTube",str(exc)); return
        self.source_url=f"https://www.youtube.com/watch?v={video_id}"
        self.source_url_edit.setText(self.source_url)
        QDesktopServices.openUrl(QUrl(self.source_url))

    @staticmethod
    def fmt(seconds):
        s=int(seconds); return f"{s//3600:02}:{(s%3600)//60:02}:{s%60:02}"

    def render_clip(self):
        if not self.current_video: QMessageBox.information(self,"Нужно видео","Сначала добавь исходное видео."); return
        source_url=None
        if self.source_url_edit.text().strip():
            try:
                video_id=youtube_video_id(self.source_url_edit.text())
                source_url=f"https://www.youtube.com/watch?v={video_id}"
            except ValueError as exc:
                QMessageBox.warning(self,"Проверь ссылку на источник",str(exc)); return
            if not self.rights_confirmation.isChecked():
                QMessageBox.warning(self,"Подтверди права","Подтверди, что создал исходное видео или имеешь разрешение на его обработку."); return
        start=self.start_spin.value(); end=self.end_spin.value()
        if end<=start: QMessageBox.warning(self,"Проверь таймкод","Время окончания должно быть больше времени начала."); return
        if self.video_info and end>self.video_info['duration']+0.1: QMessageBox.warning(self,"Проверь таймкод","Конец фрагмента выходит за длительность исходного видео."); return
        ratio="9:16" if self.ratio.currentIndex()==0 else ("1:1" if self.ratio.currentIndex()==1 else "16:9")
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); output=str(EXPORTS/f"clip_{stamp}_{uuid.uuid4().hex[:4]}.mp4")
        commentary=self.commentary_edit.toPlainText().strip()
        if len(commentary)>180:
            QMessageBox.warning(self,"Слишком длинный текст","Комментарий должен быть не длиннее 180 символов."); return
        overlay_path=None
        if commentary:
            overlay_path=str(PROJECTS/f"commentary_{uuid.uuid4().hex}.png")
            try:
                create_commentary_overlay(commentary,ratio,Path(overlay_path))
            except Exception as exc:
                QMessageBox.critical(self,"Не удалось подготовить оформление",str(exc)); return
        self.pending_export_metadata[output]={
            "created_at":datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_file":Path(self.current_video).name,
            "source_url":source_url,
            "clip_start_seconds":start,
            "clip_end_seconds":end,
            "aspect_ratio":ratio,
            "author_commentary":commentary,
        }
        if overlay_path: self.pending_overlay_paths[output]=overlay_path
        self.render_btn.setEnabled(False); self.progress.show()
        self.worker=RenderWorker(self.current_video,start,end,output,ratio,overlay_path); self.worker.done.connect(self.render_done); self.worker.failed.connect(self.render_failed); self.worker.start()

    def start_ai_analysis(self):
        if not self.current_video or not self.video_info:
            QMessageBox.information(self, "Нужно видео", "Сначала добавь исходное видео на вкладке «Обзор»."); return
        if self.ai_worker and self.ai_worker.isRunning(): return
        model = "small" if self.whisper_choice.currentIndex()==0 else ("medium" if self.whisper_choice.currentIndex()==1 else "large-v3-turbo")
        self.ai_run_btn.setEnabled(False); self.ai_progress.show(); self.ai_status.setText("Расшифровка речи и поиск лучших моментов… Первый запуск может скачать модель.")
        self.ai_worker=AIAnalysisWorker(self.current_video, self.video_info["duration"], model)
        self.ai_worker.completed.connect(self.ai_analysis_done); self.ai_worker.failed.connect(self.ai_analysis_failed); self.ai_worker.start()

    def ai_analysis_done(self, segments, clips, info):
        self.ai_run_btn.setEnabled(True); self.ai_progress.hide(); self.transcript_segments=segments; self.ai_clips=clips
        self.ai_status.setText(f"Готово: найдено {len(clips)} фрагментов; распознано сегментов речи: {len(segments)}. {info}")
        self.ai_table.setRowCount(len(clips))
        for i,c in enumerate(clips):
            values=[str(c.get("score", "—")), c.get("title", c.get("reason", "AI clip")), self.fmt(c["start"]), self.fmt(c["end"]), c.get("reason", "")]
            for j,value in enumerate(values): self.ai_table.setItem(i,j,QTableWidgetItem(value))
            self.ai_table.item(i,0).setData(Qt.UserRole, i)
        if not clips: self.ai_status.setText(self.ai_status.text()+" Речевых фрагментов для нарезки не найдено.")

    def ai_analysis_failed(self, error):
        self.ai_run_btn.setEnabled(True); self.ai_progress.hide(); self.ai_status.setText("Ошибка AI-анализа")
        QMessageBox.critical(self, "AI-анализ не выполнен", error)

    def use_selected_ai_clip(self):
        row=self.ai_table.currentRow()
        if row<0 or row>=len(self.ai_clips):
            QMessageBox.information(self, "Выбери фрагмент", "Выдели строку в таблице AI Analyzer."); return
        clip=self.ai_clips[row]; self.start_spin.setValue(float(clip["start"])); self.end_spin.setValue(float(clip["end"]))
        self.status.setText("AI-фрагмент выбран — можно перейти в «Обзор» и рендерить.")

    def select_ai_clip(self, row, column):
        self.use_selected_ai_clip()

    def render_done(self,path):
        self.render_btn.setEnabled(True); self.progress.hide()
        metadata=self.pending_export_metadata.pop(path,None)
        if metadata:
            try:
                Path(path).with_suffix(".json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self,"Метаданные экспорта",f"Клип готов, но файл с источником и комментарием сохранить не удалось:\n{exc}")
        self.cleanup_render_overlay(path); self.refresh_exports(); QMessageBox.information(self,"Готово",f"Клип сохранён:\n{path}")

    def render_failed(self,error):
        self.render_btn.setEnabled(True); self.progress.hide(); self.pending_export_metadata.pop(self.worker.output,None); self.cleanup_render_overlay(self.worker.output); QMessageBox.critical(self,"Ошибка рендеринга",error)

    def cleanup_render_overlay(self,path):
        overlay=self.pending_overlay_paths.pop(path,None)
        if overlay:
            try: Path(overlay).unlink(missing_ok=True)
            except OSError: pass

    def refresh_exports(self):
        files=sorted(EXPORTS.glob("*.mp4"),key=lambda p:p.stat().st_mtime,reverse=True)
        self.exports.clear()
        for p in files[:8]: self.exports.addItem(QListWidgetItem(p.name))
        if hasattr(self,"export_table"):
            self.export_table.setRowCount(len(files))
            for i,p in enumerate(files): self.export_table.setItem(i,0,QTableWidgetItem(p.name)); self.export_table.setItem(i,1,QTableWidgetItem(str(p)))


def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setFont(QFont("Segoe UI",10)); w=MainWindow(); w.show(); sys.exit(app.exec())
if __name__=="__main__": main()
