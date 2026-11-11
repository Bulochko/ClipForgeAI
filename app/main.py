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
ROOT = Path.home() / "Videos" / "ClipForge AI"
PROJECTS = ROOT / "Projects"
EXPORTS = ROOT / "Exports"
for folder in (PROJECTS, EXPORTS): folder.mkdir(parents=True, exist_ok=True)


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
    def __init__(self, source: str, start: float, end: float, output: str, ratio: str):
        super().__init__(); self.source=source; self.start_at=start; self.end_at=end; self.output=output; self.ratio=ratio
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
        settings=QWidget(); sv=QVBoxLayout(settings); sv.addWidget(QLabel("Локальные настройки")); sv.addWidget(QLabel(f"Рабочая папка: {ROOT}")); sv.addWidget(QLabel("FFmpeg и FFprobe должны быть доступны через PATH или лежать в папке tools рядом с программой.")); sv.addStretch(); tabs.addTab(settings,"Настройки")
        foot=QLabel("CLIPFORGE AI  •  WINDOWS FULL BUILD  •  0.3.0"); foot.setObjectName("Muted"); main.addWidget(foot)

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

    @staticmethod
    def fmt(seconds):
        s=int(seconds); return f"{s//3600:02}:{(s%3600)//60:02}:{s%60:02}"

    def render_clip(self):
        if not self.current_video: QMessageBox.information(self,"Нужно видео","Сначала добавь исходное видео."); return
        start=self.start_spin.value(); end=self.end_spin.value()
        if end<=start: QMessageBox.warning(self,"Проверь таймкод","Время окончания должно быть больше времени начала."); return
        if self.video_info and end>self.video_info['duration']+0.1: QMessageBox.warning(self,"Проверь таймкод","Конец фрагмента выходит за длительность исходного видео."); return
        ratio="9:16" if self.ratio.currentIndex()==0 else ("1:1" if self.ratio.currentIndex()==1 else "16:9")
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); output=str(EXPORTS/f"clip_{stamp}_{uuid.uuid4().hex[:4]}.mp4")
        self.render_btn.setEnabled(False); self.progress.show()
        self.worker=RenderWorker(self.current_video,start,end,output,ratio); self.worker.done.connect(self.render_done); self.worker.failed.connect(self.render_failed); self.worker.start()

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
        self.render_btn.setEnabled(True); self.progress.hide(); self.refresh_exports(); QMessageBox.information(self,"Готово",f"Клип сохранён:\n{path}")

    def render_failed(self,error):
        self.render_btn.setEnabled(True); self.progress.hide(); QMessageBox.critical(self,"Ошибка рендеринга",error)

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
