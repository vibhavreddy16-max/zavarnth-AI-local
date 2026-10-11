from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from ..ai import GeminiService
from ..audio.live import LiveVoiceWorker
from ..config import DATA_DIR, Settings, delete_api_key, get_api_key, save_api_key
from ..database import Database
from ..memory import MemoryStore
from ..monitoring import TelemetryWorker
from ..plugins import PluginManager
from ..task_agent import TaskAgentWorker
from ..tools.builtins import ToolExecutor
from .styles import STYLESHEET
from .widgets import AvatarWidget, MetricCard, WaveformWidget, small_label
from .workers import ChatWorker, ScreenshotWorker, SearchWorker, SingleToolWorker


NAV_ITEMS = [
    ("◈", "Conversation"),
    ("⌁", "Task agent"),
    ("▤", "Web research"),
    ("▧", "System"),
    ("◉", "Memory"),
    ("⚙", "Settings"),
    ("≋", "Activity"),
]


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    return frame


def heading(title: str, subtitle: str) -> QVBoxLayout:
    layout = QVBoxLayout()
    eyebrow = QLabel("ZYVARNTH  /  CONTROL DECK")
    eyebrow.setObjectName("Eyebrow")
    label = QLabel(title)
    label.setObjectName("PageTitle")
    sub = QLabel(subtitle)
    sub.setObjectName("Muted")
    layout.addWidget(eyebrow)
    layout.addWidget(label)
    layout.addWidget(sub)
    return layout


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zyvarnth — Personal AI Control Deck")
        self.setMinimumSize(1080, 720)
        self.resize(1440, 920)
        self.setStyleSheet(STYLESHEET)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = Settings()
        self.database = Database()
        self.memory = MemoryStore(self.database)
        self.ai = GeminiService(self.settings, self.memory)
        self.tools = ToolExecutor(self.settings, self.database)
        self.plugin_manager = PluginManager(self.settings, self.tools.registry)
        self.plugin_results = self.plugin_manager.load_enabled()
        self.telemetry: TelemetryWorker | None = None
        self.chat_worker: ChatWorker | None = None
        self.voice_worker: LiveVoiceWorker | None = None
        self.task_worker: TaskAgentWorker | None = None
        self.single_tool_worker: SingleToolWorker | None = None
        self.screenshot_worker: ScreenshotWorker | None = None
        self.current_image: bytes | None = None
        self._fullscreen = False
        self._task_paused = False
        self._voice_user = ""
        self._voice_assistant = ""
        sessions = self.database.list_sessions(1)
        self.session_id = sessions[0]["id"] if sessions else self.database.create_session("Conversation")
        self.transcript: list[dict[str, str]] = self.database.messages(self.session_id)

        self._build_shell()
        self._build_pages()
        self._refresh_session_history()
        self._render_conversation()
        self._update_credential_status()
        self._start_telemetry()
        self._start_reminder_timer()

    def _build_shell(self) -> None:
        root = QWidget()
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(218)
        nav = QVBoxLayout(self.sidebar)
        nav.setContentsMargins(14, 20, 14, 18)
        nav.setSpacing(7)
        brand = QLabel("◉  ZYVARNTH")
        brand.setObjectName("Brand")
        nav.addWidget(brand)
        version = QLabel("PERSONAL INTELLIGENCE  /  01")
        version.setObjectName("Eyebrow")
        nav.addWidget(version)
        nav.addSpacing(20)
        self.nav_buttons: list[QPushButton] = []
        for index, (icon, name) in enumerate(NAV_ITEMS):
            button = QPushButton(f"{icon}   {name}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._navigate(page))
            self.nav_buttons.append(button)
            nav.addWidget(button)
        nav.addStretch(1)
        nav_note = QLabel("LOCAL MEMORY\nEXPLICIT CAPTURE\nAPPROVED ACTIONS")
        nav_note.setObjectName("Eyebrow")
        nav_note.setStyleSheet("line-height: 1.7;")
        nav.addWidget(nav_note)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(22, 12, 20, 12)
        self.breadcrumb = QLabel("CONVERSATION  /  LIVE SESSION")
        self.breadcrumb.setObjectName("Eyebrow")
        self.top_status = QLabel("●  LOCAL / READY")
        self.top_status.setStyleSheet("color: #79d7c5; font-weight: 600;")
        self.compact_button = QPushButton("COMPACT")
        self.compact_button.setCheckable(True)
        self.compact_button.setChecked(bool(self.settings.get("compact_mode", False)))
        self.compact_button.clicked.connect(self._toggle_compact)
        self.fullscreen_button = QPushButton("⛶  IMMERSIVE")
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self.stop_button = QPushButton("■  EMERGENCY STOP")
        self.stop_button.setObjectName("Danger")
        self.stop_button.clicked.connect(self.emergency_stop)
        top_layout.addWidget(self.breadcrumb)
        top_layout.addStretch(1)
        top_layout.addWidget(self.top_status)
        top_layout.addWidget(self.compact_button)
        top_layout.addWidget(self.fullscreen_button)
        top_layout.addWidget(self.stop_button)

        self.stack = QStackedWidget()
        body.addWidget(top)
        body.addWidget(self.stack, 1)
        self.status_line = QLabel("Zyvarnth is ready. Add a Gemini API key in Settings to connect.")
        self.status_line.setObjectName("Muted")
        self.status_line.setStyleSheet("padding: 8px 18px; border-top: 1px solid #172733;")
        body.addWidget(self.status_line)
        shell.addWidget(self.sidebar)
        body_widget = QWidget()
        body_widget.setLayout(body)
        shell.addWidget(body_widget, 1)
        self.setCentralWidget(root)

    def _build_pages(self) -> None:
        self.conversation_page = self._build_conversation_page()
        self.task_page = self._build_task_page()
        self.research_page = self._build_research_page()
        self.system_page = self._build_system_page()
        self.memory_page = self._build_memory_page()
        self.settings_page = self._build_settings_page()
        self.activity_page = self._build_activity_page()
        for widget in [self.conversation_page, self.task_page, self.research_page, self.system_page,
                       self.memory_page, self.settings_page, self.activity_page]:
            self.stack.addWidget(widget)
        self._navigate(0)

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        title = NAV_ITEMS[index][1].upper()
        self.breadcrumb.setText(f"{title}  /  CONTROL DECK")
        if index == 4:
            self._refresh_memories()
        elif index == 6:
            self._refresh_activity()

    def _build_conversation_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(14)
        top = QHBoxLayout()
        title = QVBoxLayout()
        eyebrow = QLabel("AI CONVERSATION  /  TEXT + LIVE VOICE")
        eyebrow.setObjectName("Eyebrow")
        heading_label = QLabel("Conversation")
        heading_label.setObjectName("PageTitle")
        subtitle = QLabel("Streaming Gemini replies with optional, push-to-talk audio.")
        subtitle.setObjectName("Muted")
        title.addWidget(eyebrow)
        title.addWidget(heading_label)
        title.addWidget(subtitle)
        top.addLayout(title)
        top.addStretch(1)
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(210)
        self.session_combo.currentIndexChanged.connect(self._select_session)
        self.new_session_button = QPushButton("＋  New conversation")
        self.new_session_button.clicked.connect(self._new_session)
        top.addWidget(self.session_combo)
        top.addWidget(self.new_session_button)
        layout.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        main_panel = panel()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)
        hero = QHBoxLayout()
        avatar_column = QVBoxLayout()
        self.avatar = AvatarWidget()
        self.voice_state_label = QLabel("READY  /  AWAITING INPUT")
        self.voice_state_label.setObjectName("Eyebrow")
        self.waveform = WaveformWidget()
        avatar_column.addWidget(self.avatar, 1, Qt.AlignmentFlag.AlignCenter)
        avatar_column.addWidget(self.voice_state_label, 0, Qt.AlignmentFlag.AlignCenter)
        avatar_column.addWidget(self.waveform)
        hero.addLayout(avatar_column, 1)
        self.quick_panel = QFrame()
        self.quick_panel.setObjectName("Card")
        quick = QVBoxLayout(self.quick_panel)
        quick.setContentsMargins(15, 13, 15, 13)
        quick.addWidget(QLabel("SESSION SIGNAL"), 0)
        self.gemini_indicator = QLabel("◌  GEMINI  /  NOT CONFIGURED")
        self.gemini_indicator.setObjectName("Muted")
        self.memory_indicator = QLabel("◈  MEMORY  /  ON")
        self.memory_indicator.setObjectName("Muted")
        self.os_indicator = QLabel("▣  PLATFORM  /  DETECTING")
        self.os_indicator.setObjectName("Muted")
        self.screenshot_label = QLabel("SCREEN ANALYSIS\nNo capture provided")
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setMinimumSize(190, 130)
        self.screenshot_label.setMaximumHeight(190)
        self.screenshot_label.setStyleSheet("color:#64808b; border:1px dashed #29434f; border-radius:8px;")
        self.quick_compact_widgets = [self.gemini_indicator, self.memory_indicator, self.os_indicator, self.screenshot_label]
        quick.addWidget(self.gemini_indicator)
        quick.addWidget(self.memory_indicator)
        quick.addWidget(self.os_indicator)
        quick.addSpacing(6)
        quick.addWidget(self.screenshot_label, 1)
        quick.addWidget(small_label("Avatar articulation follows speech transcription; waveform follows captured audio.", True))
        hero.addWidget(self.quick_panel, 0)
        self.chat_secondary = self.quick_panel
        main_layout.addLayout(hero, 4)
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.setMinimumHeight(180)
        self.chat_view.setStyleSheet("background:#080f16; border:1px solid #1a303c; border-radius:9px; padding:8px;")
        main_layout.addWidget(self.chat_view, 3)
        self.live_transcript_label = QLabel("")
        self.live_transcript_label.setObjectName("Muted")
        main_layout.addWidget(self.live_transcript_label)
        composer = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Ask Zyvarnth something…")
        self.message_input.returnPressed.connect(self._send_message)
        self.send_button = QPushButton("SEND  ↗")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self._send_message)
        self.cancel_chat_button = QPushButton("CANCEL")
        self.cancel_chat_button.setEnabled(False)
        self.cancel_chat_button.clicked.connect(self._cancel_chat)
        self.capture_button = QPushButton("▣  ANALYZE SCREEN")
        self.capture_button.setToolTip("Capture and send a screenshot only after this explicit request.")
        self.capture_button.clicked.connect(self._capture_screen)
        composer.addWidget(self.message_input, 1)
        composer.addWidget(self.capture_button)
        composer.addWidget(self.send_button)
        composer.addWidget(self.cancel_chat_button)
        main_layout.addLayout(composer)
        controls = QHBoxLayout()
        self.connect_voice_button = QPushButton("◉  CONNECT LIVE VOICE")
        self.connect_voice_button.clicked.connect(self._toggle_voice_link)
        self.ptt_button = QPushButton("HOLD TO TALK  ·  WINDOW HOTKEY: CTRL + SPACE")
        self.ptt_button.setEnabled(False)
        self.ptt_button.setToolTip("Microphone capture begins only while this button is held.")
        self.ptt_button.pressed.connect(self._ptt_pressed)
        self.ptt_button.released.connect(self._ptt_released)
        controls.addWidget(self.connect_voice_button)
        controls.addWidget(self.ptt_button)
        controls.addStretch(1)
        controls.addWidget(small_label("MICROPHONE CLOSED UNTIL PUSH-TO-TALK", True))
        main_layout.addLayout(controls)
        split.addWidget(main_panel)
        layout.addWidget(split, 1)
        self._toggle_compact(self.compact_button.isChecked())
        return page

    def _build_task_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        top = heading("Task agent", "Build a validated plan, inspect each step, pause it, or stop it at any time.")
        layout.addLayout(top)
        form = panel()
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.addWidget(small_label("TASK GOAL", True))
        self.task_goal = QLineEdit()
        self.task_goal.setPlaceholderText("Research three project management tools and prepare a sourced comparison…")
        form_layout.addWidget(self.task_goal)
        buttons = QHBoxLayout()
        self.plan_button = QPushButton("PLAN  /  RUN")
        self.plan_button.setObjectName("Primary")
        self.plan_button.clicked.connect(self._start_task)
        self.pause_button = QPushButton("PAUSE")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._pause_task)
        self.resume_button = QPushButton("RESUME")
        self.resume_button.setEnabled(False)
        self.resume_button.clicked.connect(self._resume_task)
        self.cancel_task_button = QPushButton("CANCEL TASK")
        self.cancel_task_button.setObjectName("Danger")
        self.cancel_task_button.setEnabled(False)
        self.cancel_task_button.clicked.connect(self._cancel_task)
        buttons.addWidget(self.plan_button)
        buttons.addWidget(self.pause_button)
        buttons.addWidget(self.resume_button)
        buttons.addWidget(self.cancel_task_button)
        buttons.addStretch(1)
        form_layout.addLayout(buttons)
        layout.addWidget(form)

        direct = panel()
        direct_layout = QVBoxLayout(direct)
        direct_layout.setContentsMargins(16, 13, 16, 13)
        direct_layout.addWidget(small_label("DIRECT TOOL EXECUTION  /  EVERY INPUT IS VALIDATED", True))
        row = QHBoxLayout()
        self.tool_combo = QComboBox()
        for spec in self.tools.registry.all():
            self.tool_combo.addItem(f"{spec.name}  ·  {spec.description}", spec.name)
        self.tool_args = QPlainTextEdit("{}")
        self.tool_args.setPlaceholderText('{"url":"https://…"}')
        self.tool_args.setMaximumHeight(70)
        self.tool_run_button = QPushButton("RUN TOOL")
        self.tool_run_button.clicked.connect(self._run_direct_tool)
        row.addWidget(self.tool_combo, 2)
        row.addWidget(self.tool_args, 2)
        row.addWidget(self.tool_run_button)
        direct_layout.addLayout(row)
        direct_layout.addWidget(small_label("Consequential actions require an approval dialog. No general shell tool is exposed.", True))
        layout.addWidget(direct)

        task_panel = panel()
        task_layout = QVBoxLayout(task_panel)
        task_layout.setContentsMargins(16, 14, 16, 14)
        task_layout.addWidget(small_label("EXECUTION TRACE", True))
        self.task_trace = QTextBrowser()
        self.task_trace.setMinimumHeight(140)
        self.task_trace.setStyleSheet("background:#080f16; border:1px solid #1a303c; border-radius:8px; padding:8px;")
        self.task_result = QTextBrowser()
        self.task_result.setMinimumHeight(125)
        self.task_result.setStyleSheet("background:#09141b; border:1px solid #1b3945; border-radius:8px; padding:8px;")
        task_layout.addWidget(self.task_trace, 1)
        task_layout.addWidget(QLabel("FINAL REPORT / RESULT"))
        task_layout.addWidget(self.task_result, 1)
        layout.addWidget(task_panel, 1)
        return page

    def _build_research_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.addLayout(heading("Web research", "Live search results from DuckDuckGo with source links and visible excerpts."))
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for current information…")
        self.search_input.returnPressed.connect(self._run_search)
        self.search_button = QPushButton("SEARCH WEB")
        self.search_button.setObjectName("Primary")
        self.search_button.clicked.connect(self._run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)
        self.research_status = QLabel("Search is not run until you submit a query.")
        self.research_status.setObjectName("Muted")
        layout.addWidget(self.research_status)
        self.research_scroll = QScrollArea()
        self.research_scroll.setWidgetResizable(True)
        self.research_content = QWidget()
        self.research_results_layout = QVBoxLayout(self.research_content)
        self.research_results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.research_scroll.setWidget(self.research_content)
        layout.addWidget(self.research_scroll, 1)
        self.search_worker: SearchWorker | None = None
        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.addLayout(heading("System monitor", "Live telemetry is read from the local OS through psutil; unavailable sensors stay marked unavailable."))
        self.system_platform = QLabel("Waiting for first telemetry sample…")
        self.system_platform.setObjectName("Muted")
        layout.addWidget(self.system_platform)
        grid = QHBoxLayout()
        col_a = QVBoxLayout()
        col_b = QVBoxLayout()
        self.metric_cards = {
            "cpu": MetricCard("CPU load"),
            "memory": MetricCard("Memory"),
            "disk": MetricCard("Root disk"),
            "battery": MetricCard("Battery"),
            "temperature": MetricCard("Temperature"),
        }
        col_a.addWidget(self.metric_cards["cpu"])
        col_a.addWidget(self.metric_cards["memory"])
        col_a.addWidget(self.metric_cards["disk"])
        col_b.addWidget(self.metric_cards["battery"])
        col_b.addWidget(self.metric_cards["temperature"])
        note = panel()
        note_layout = QVBoxLayout(note)
        note_layout.addWidget(QLabel("DEVICE CAPABILITIES"))
        self.system_capabilities = QLabel("Computer actions use dedicated OS adapters. Permission failures and unsupported sensors are reported per capability.")
        self.system_capabilities.setWordWrap(True)
        self.system_capabilities.setObjectName("Muted")
        note_layout.addWidget(self.system_capabilities)
        col_b.addWidget(note)
        grid.addLayout(col_a, 1)
        grid.addLayout(col_b, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _build_memory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.addLayout(heading("Memory manager", "Inspect and edit user-approved facts. Conversation history is stored separately."))
        self.memory_state_label = QLabel("")
        self.memory_state_label.setObjectName("Muted")
        layout.addWidget(self.memory_state_label)
        controls = QHBoxLayout()
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("Search saved memories…")
        self.memory_search.textChanged.connect(self._refresh_memories)
        add = QPushButton("＋  ADD APPROVED FACT")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_memory)
        erase = QPushButton("ERASE ALL")
        erase.setObjectName("Danger")
        erase.clicked.connect(self._erase_memories)
        controls.addWidget(self.memory_search, 1)
        controls.addWidget(add)
        controls.addWidget(erase)
        layout.addLayout(controls)
        self.memory_list = QListWidget()
        self.memory_list.itemDoubleClicked.connect(self._edit_selected_memory)
        layout.addWidget(self.memory_list, 1)
        row = QHBoxLayout()
        edit = QPushButton("EDIT SELECTED")
        edit.clicked.connect(self._edit_selected_memory)
        delete = QPushButton("DELETE SELECTED")
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete_selected_memory)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.addLayout(heading("Settings & permissions", "Credentials stay in the OS keychain. Choose approved folders and voice behavior here."))
        content = panel()
        form = QVBoxLayout(content)
        form.setContentsMargins(18, 16, 18, 16)
        form.addWidget(QLabel("GEMINI CONNECTION"))
        key_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Paste a Google Gemini API key — stored only when you press Save")
        save_key = QPushButton("SAVE TO KEYCHAIN")
        save_key.setObjectName("Primary")
        save_key.clicked.connect(self._save_key)
        clear_key = QPushButton("REMOVE SAVED KEY")
        clear_key.setObjectName("Danger")
        clear_key.clicked.connect(self._delete_key)
        key_row.addWidget(self.api_key_input, 1)
        key_row.addWidget(save_key)
        key_row.addWidget(clear_key)
        form.addLayout(key_row)
        self.credential_status = QLabel("")
        self.credential_status.setObjectName("Muted")
        form.addWidget(self.credential_status)

        model_row = QHBoxLayout()
        self.text_model_input = QLineEdit(str(self.settings.get("text_model")))
        self.live_model_input = QLineEdit(str(self.settings.get("live_model")))
        model_row.addWidget(QLabel("Text model"))
        model_row.addWidget(self.text_model_input, 1)
        model_row.addWidget(QLabel("Live model"))
        model_row.addWidget(self.live_model_input, 1)
        form.addLayout(model_row)
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Voice"))
        self.voice_combo = QComboBox()
        for voice in ["Aoede", "Puck", "Charon", "Kore", "Fenrir"]:
            self.voice_combo.addItem(voice)
        self.voice_combo.setCurrentText(str(self.settings.get("voice", "Aoede")))
        voice_row.addWidget(self.voice_combo)
        voice_row.addStretch(1)
        self.memory_enabled = QCheckBox("Use relevant approved memories in Gemini prompts")
        self.memory_enabled.setChecked(bool(self.settings.get("memory_enabled", True)))
        voice_row.addWidget(self.memory_enabled)
        form.addLayout(voice_row)

        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Microphone"))
        self.input_device_combo = QComboBox()
        audio_row.addWidget(self.input_device_combo, 1)
        audio_row.addWidget(QLabel("Speakers"))
        self.output_device_combo = QComboBox()
        audio_row.addWidget(self.output_device_combo, 1)
        form.addLayout(audio_row)
        self.audio_device_status = QLabel("")
        self.audio_device_status.setObjectName("Muted")
        form.addWidget(self.audio_device_status)
        self._refresh_audio_devices()

        form.addSpacing(8)
        form.addWidget(QLabel("APPROVED FILE ROOTS"))
        roots_row = QHBoxLayout()
        self.root_list = QListWidget()
        self.root_list.setMaximumHeight(105)
        self._refresh_roots()
        root_buttons = QVBoxLayout()
        add_root = QPushButton("ADD FOLDER")
        add_root.clicked.connect(self._add_root)
        remove_root = QPushButton("REMOVE SELECTED")
        remove_root.clicked.connect(self._remove_root)
        root_buttons.addWidget(add_root)
        root_buttons.addWidget(remove_root)
        root_buttons.addStretch(1)
        roots_row.addWidget(self.root_list, 1)
        roots_row.addLayout(root_buttons)
        form.addLayout(roots_row)
        form.addWidget(small_label("File tools cannot read or change paths outside these folders. Choose only locations you want Zyvarnth to access.", True))

        form.addSpacing(8)
        form.addWidget(QLabel("LOCAL PLUGINS  /  TRUSTED CODE"))
        self.plugin_list = QListWidget()
        self.plugin_list.setMaximumHeight(110)
        self._refresh_plugins()
        form.addWidget(self.plugin_list)
        form.addWidget(small_label(f"Plugin folder: {self.plugin_manager.directory} — enabling a plugin runs its local Python code after app restart.", True))

        save = QPushButton("SAVE SETTINGS")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_settings)
        form.addWidget(save, 0, Qt.AlignmentFlag.AlignRight)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.addLayout(heading("Activity & undo", "The local journal records tool outcomes. Undo checks file contents and paths before restoring them."))
        refresh = QPushButton("REFRESH JOURNAL")
        refresh.clicked.connect(self._refresh_activity)
        layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignRight)
        self.activity_scroll = QScrollArea()
        self.activity_scroll.setWidgetResizable(True)
        self.activity_content = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_content)
        self.activity_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.activity_scroll.setWidget(self.activity_content)
        layout.addWidget(self.activity_scroll, 1)
        return page

    def _refresh_session_history(self) -> None:
        if not hasattr(self, "session_combo"):
            return
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        sessions = self.database.list_sessions()
        for session in sessions:
            self.session_combo.addItem(session["title"], session["id"])
            if session["id"] == self.session_id:
                self.session_combo.setCurrentIndex(self.session_combo.count() - 1)
        self.session_combo.blockSignals(False)

    def _select_session(self, index: int) -> None:
        session_id = self.session_combo.itemData(index)
        if not session_id or session_id == self.session_id:
            return
        self.session_id = session_id
        self.transcript = self.database.messages(self.session_id)
        self._render_conversation()

    def _new_session(self) -> None:
        self.session_id = self.database.create_session("Conversation " + datetime.now().astimezone().strftime("%b %d, %H:%M"))
        self.transcript = []
        self.current_image = None
        self.screenshot_label.setPixmap(QPixmap())
        self.screenshot_label.setText("SCREEN ANALYSIS\nNo capture provided")
        self._refresh_session_history()
        self._render_conversation()

    def _render_conversation(self) -> None:
        blocks = []
        for message in self.transcript:
            role = message.get("role", "assistant")
            label = "YOU" if role == "user" else "ZYVARNTH" if role == "assistant" else "TOOL"
            color = "#55cfdf" if role == "user" else "#c5e8ef"
            content = html.escape(message.get("content", "")).replace("\n", "<br>")
            blocks.append(
                f"<div style='margin:10px 4px 14px;padding:10px 12px;background:#0c1720;"
                f"border-left:2px solid {color};border-radius:5px;'>"
                f"<span style='color:{color};font-size:10px;letter-spacing:2px;font-weight:bold'>{label}</span>"
                f"<div style='color:#d5e6ec;line-height:1.55;margin-top:5px;white-space:pre-wrap'>{content}</div></div>"
            )
        if not blocks:
            blocks.append("<div style='color:#6d8996;margin:20px'>Start a text conversation or connect voice. Gemini replies stream into this panel.</div>")
        self.chat_view.setHtml("<html><body style='background:#080f16;color:#d7e5ed;font-family:Arial;font-size:13px'>" + "".join(blocks) + "</body></html>")
        cursor = self.chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_view.setTextCursor(cursor)

    def _send_message(self, text_override: str | None = None) -> None:
        if self.chat_worker and self.chat_worker.isRunning():
            return
        text = (text_override if text_override is not None else self.message_input.text()).strip()
        if not text:
            return
        self.message_input.clear()
        self.transcript.append({"role": "user", "content": text})
        self.database.append_message(self.session_id, "user", text)
        self._refresh_session_history()
        self._render_conversation()
        self.send_button.setEnabled(False)
        self.cancel_chat_button.setEnabled(True)
        self.voice_state_label.setText("THINKING  /  GEMINI REQUEST ACTIVE")
        self.avatar.set_state("Thinking")
        recent = self.database.messages(self.session_id, 18)
        recent_signatures = {(item["role"], item["content"], item["created_at"]) for item in recent}
        relevant = [
            item for item in self.database.relevant_messages(self.session_id, text, 6)
            if (item["role"], item["content"], item["created_at"]) not in recent_signatures
        ]
        messages = relevant + recent
        image, self.current_image = self.current_image, None
        self.chat_worker = ChatWorker(self.ai, messages, image, self)
        self.chat_worker.text_delta.connect(self._chat_delta)
        self.chat_worker.completed.connect(self._chat_completed)
        self.chat_worker.failed.connect(self._chat_failed)
        self.chat_worker.cancelled.connect(self._chat_cancelled)
        self.chat_worker.finished.connect(self._chat_thread_finished)
        self.chat_worker.start()

    def _chat_delta(self, text: str) -> None:
        if not self.transcript or self.transcript[-1]["role"] != "assistant" or not getattr(self, "_streaming_response", False):
            self.transcript.append({"role": "assistant", "content": ""})
            self._streaming_response = True
        self.transcript[-1]["content"] += text
        self._render_conversation()

    def _chat_completed(self, text: str) -> None:
        if text:
            if not self.transcript or self.transcript[-1]["role"] != "assistant":
                self.transcript.append({"role": "assistant", "content": text})
            self.transcript[-1]["content"] = text
            self.database.append_message(self.session_id, "assistant", text)
        self._streaming_response = False
        self._render_conversation()
        self.voice_state_label.setText("READY  /  RESPONSE COMPLETE")
        self.avatar.set_state("Ready")

    def _chat_failed(self, message: str) -> None:
        self._discard_partial_response()
        self._streaming_response = False
        self.voice_state_label.setText("ERROR  /  REQUEST FAILED")
        self.avatar.set_state("Error")
        self.status_line.setText(message)
        QMessageBox.warning(self, "Gemini request failed", message)

    def _chat_cancelled(self) -> None:
        self._discard_partial_response()
        self._streaming_response = False
        self.voice_state_label.setText("CANCELLED  /  REQUEST STOPPED")
        self.avatar.set_state("Ready")
        self.status_line.setText("Gemini request cancelled.")

    def _discard_partial_response(self) -> None:
        if (getattr(self, "_streaming_response", False) and self.transcript
                and self.transcript[-1]["role"] == "assistant"):
            self.transcript.pop()
            self._render_conversation()

    def _chat_thread_finished(self) -> None:
        self.send_button.setEnabled(True)
        self.cancel_chat_button.setEnabled(False)

    def _cancel_chat(self) -> None:
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.cancel()
            self.cancel_chat_button.setEnabled(False)

    def _capture_screen(self) -> None:
        if self.screenshot_worker and self.screenshot_worker.isRunning():
            return
        self.capture_button.setEnabled(False)
        self.status_line.setText("Capturing the screen after your request…")
        self.screenshot_worker = ScreenshotWorker(self)
        self.screenshot_worker.captured.connect(self._screen_captured)
        self.screenshot_worker.failed.connect(self._screen_failed)
        self.screenshot_worker.finished.connect(lambda: self.capture_button.setEnabled(True))
        self.screenshot_worker.start()

    def _screen_captured(self, data: bytes) -> None:
        self.current_image = data
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        self.screenshot_label.setPixmap(pixmap.scaled(self.screenshot_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.screenshot_label.setText("")
        self.status_line.setText("Screenshot captured successfully. Sending it to Gemini for analysis.")
        self._send_message("Please analyze the screenshot I explicitly requested. Explain visible content or errors and suggest a next step.")

    def _screen_failed(self, message: str) -> None:
        self.status_line.setText("Screenshot capture failed. No screen content was sent.")
        QMessageBox.warning(self, "Screen capture failed", message)

    def _toggle_voice_link(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop()
            self.connect_voice_button.setText("CONNECTING DOWN…")
            return
        worker = LiveVoiceWorker(self.settings, self)
        worker.status_changed.connect(self._voice_status)
        worker.user_transcript.connect(self._voice_user_text)
        worker.assistant_transcript.connect(self._voice_assistant_text)
        worker.audio_level.connect(self._audio_level)
        worker.audio_advanced.connect(self.avatar.advance_audio)
        worker.turn_finished.connect(self._voice_turn_finished)
        worker.error.connect(self._voice_error)
        worker.finished.connect(self._voice_finished)
        self.voice_worker = worker
        self.connect_voice_button.setText("CONNECTING…")
        worker.start()

    def _voice_status(self, state: str) -> None:
        self.voice_state_label.setText(f"{state.upper()}  /  LIVE VOICE")
        self.avatar.set_state(state)
        self.waveform.set_active(state in {"Listening", "Speaking"})
        self.ptt_button.setEnabled(state not in {"Connecting", "Error"} and self.voice_worker is not None)
        self.connect_voice_button.setText("DISCONNECT VOICE" if self.voice_worker and self.voice_worker.isRunning() else "◉  CONNECT LIVE VOICE")
        if state == "Ready":
            self._voice_turn_finished()

    def _voice_user_text(self, text: str) -> None:
        self._voice_user += text
        self.live_transcript_label.setText("HEARD  /  " + self._voice_user[-240:])

    def _voice_assistant_text(self, text: str) -> None:
        self._voice_assistant += text
        self.avatar.set_speech(text)
        self.live_transcript_label.setText("SPEAKING  /  " + self._voice_assistant[-240:])

    def _voice_turn_finished(self) -> None:
        user, assistant = self._voice_user.strip(), self._voice_assistant.strip()
        if user:
            self.transcript.append({"role": "user", "content": user})
            self.database.append_message(self.session_id, "user", user)
        if assistant:
            self.transcript.append({"role": "assistant", "content": assistant})
            self.database.append_message(self.session_id, "assistant", assistant)
        if user or assistant:
            self._refresh_session_history()
            self._render_conversation()
        self._voice_user = ""
        self._voice_assistant = ""
        self.avatar.end_speech()
        self.live_transcript_label.setText("")

    def _audio_level(self, value: float) -> None:
        self.waveform.set_level(value)
        self.avatar.set_level(value)

    def _voice_error(self, message: str) -> None:
        self.voice_state_label.setText("ERROR  /  LIVE VOICE UNAVAILABLE")
        self.avatar.set_state("Error")
        self.status_line.setText(message)

    def _voice_finished(self) -> None:
        if self.voice_worker and not self.voice_worker.isRunning():
            self.voice_worker = None
        self.connect_voice_button.setText("◉  CONNECT LIVE VOICE")
        self.ptt_button.setEnabled(False)
        self.avatar.set_state("Ready")
        self.avatar.end_speech()
        self.voice_state_label.setText("READY  /  MICROPHONE CLOSED")

    def _ptt_pressed(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.set_push_to_talk(True)

    def _ptt_released(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.set_push_to_talk(False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and event.modifiers() & Qt.KeyboardModifier.ControlModifier and not event.isAutoRepeat():
            self._ptt_pressed()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._ptt_released()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _start_task(self) -> None:
        goal = self.task_goal.text().strip()
        if not goal:
            return
        if self.task_worker and self.task_worker.isRunning():
            return
        self.task_trace.clear()
        self.task_result.clear()
        worker = TaskAgentWorker(goal, self.ai, self.tools, self)
        worker.plan_ready.connect(self._task_plan_ready)
        worker.progress.connect(self._task_progress)
        worker.approval_needed.connect(self._task_approval_needed)
        worker.completed.connect(self._task_completed)
        worker.failed.connect(self._task_failed)
        worker.cancelled.connect(lambda: self._task_progress(0, "Task cancelled. No later steps will run."))
        worker.finished.connect(self._task_finished)
        self.task_worker = worker
        self._task_controls(True)
        self.task_trace.append("Requesting a constrained plan from the configured Gemini model…")
        worker.start()

    def _task_plan_ready(self, plan: list) -> None:
        self.task_trace.append("VALIDATED PLAN")
        for number, step in enumerate(plan, 1):
            self.task_trace.append(f"{number}. {step['label']}  [{step['tool']}]")

    def _task_progress(self, index: int, message: str) -> None:
        self.task_trace.append(message)

    def _task_approval_needed(self, summary: str) -> None:
        approved = self._approval_dialog(
            "Approve computer action?",
            summary + "\n\nThis action runs only if you press Approve. The model cannot approve it for you.",
        )
        if self.task_worker:
            self.task_worker.answer_approval(approved)

    def _task_completed(self, report: str) -> None:
        self.task_result.setPlainText(report)

    def _task_failed(self, message: str) -> None:
        self.task_trace.append("ERROR  /  " + message)
        self.task_result.setPlainText("Task did not complete. No successful result is being reported.")

    def _task_finished(self) -> None:
        self._task_controls(False)
        self._refresh_activity()

    def _task_controls(self, running: bool) -> None:
        self.plan_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.cancel_task_button.setEnabled(running)
        self.resume_button.setEnabled(False)
        self._task_paused = False

    def _pause_task(self) -> None:
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.pause()
            self._task_paused = True
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
            self.task_trace.append("Task paused. No next tool will start until resumed.")

    def _resume_task(self) -> None:
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.resume()
            self._task_paused = False
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)
            self.task_trace.append("Task resumed.")

    def _cancel_task(self) -> None:
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.cancel()
            self.task_trace.append("Cancellation requested. Active operation will not schedule a later step.")

    def _run_direct_tool(self) -> None:
        name = self.tool_combo.currentData()
        try:
            arguments = json.loads(self.tool_args.toPlainText() or "{}")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Invalid tool arguments", f"The arguments must be valid JSON. {exc.msg}")
            return
        if not isinstance(arguments, dict):
            QMessageBox.warning(self, "Invalid tool arguments", "Tool arguments must be a JSON object.")
            return
        if self.single_tool_worker and self.single_tool_worker.isRunning():
            return
        worker = SingleToolWorker(self.tools, name, arguments, self)
        worker.approval_needed.connect(self._single_tool_approval)
        worker.completed.connect(lambda result: self._direct_tool_done(name, result))
        worker.failed.connect(lambda error: QMessageBox.warning(self, "Tool failed", error))
        worker.cancelled.connect(lambda: self.task_trace.append("Tool action cancelled or declined."))
        worker.finished.connect(self._refresh_activity)
        self.single_tool_worker = worker
        self.task_trace.append(f"Running validated tool: {name}")
        worker.start()

    def _single_tool_approval(self, summary: str) -> None:
        approved = self._approval_dialog(
            "Approve computer action?",
            summary + "\n\nThe action will run only after you approve it.",
        )
        if self.single_tool_worker:
            self.single_tool_worker.answer_approval(approved)

    def _approval_dialog(self, title: str, message: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        approve = dialog.addButton("Approve", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        return dialog.clickedButton() is approve

    def _direct_tool_done(self, name: str, result: str) -> None:
        self.task_trace.append(f"Completed {name}: {result}")
        self._refresh_activity()

    def _run_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        if self.search_worker and self.search_worker.isRunning():
            return
        self.search_button.setEnabled(False)
        self.research_status.setText("Searching live sources…")
        self._clear_layout(self.research_results_layout)
        worker = SearchWorker(self.tools, query, self)
        worker.results.connect(self._research_results)
        worker.failed.connect(self._research_failed)
        worker.finished.connect(lambda: self.search_button.setEnabled(True))
        self.search_worker = worker
        worker.start()

    def _research_results(self, results: list) -> None:
        self.research_status.setText(f"Search returned {len(results)} source(s). Verify details at the linked pages.")
        if not results:
            self.research_results_layout.addWidget(QLabel("No results were returned."))
        for index, result in enumerate(results, 1):
            card = panel()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            top = QHBoxLayout()
            title = QLabel(f"[{index}]  {result.get('title', 'Untitled')}")
            title.setWordWrap(True)
            open_button = QPushButton("OPEN SOURCE ↗")
            open_button.clicked.connect(lambda checked=False, url=result.get("url", ""): self._open_source(url))
            top.addWidget(title, 1)
            top.addWidget(open_button)
            snippet = QLabel(result.get("snippet", ""))
            snippet.setWordWrap(True)
            snippet.setObjectName("Muted")
            url = QLabel(result.get("url", ""))
            url.setObjectName("Eyebrow")
            card_layout.addLayout(top)
            card_layout.addWidget(snippet)
            card_layout.addWidget(url)
            self.research_results_layout.addWidget(card)

    def _research_failed(self, message: str) -> None:
        self.research_status.setText("Live search failed. No results were fabricated.")
        self.research_results_layout.addWidget(QLabel(message))

    def _open_source(self, url: str) -> None:
        try:
            from ..security import validate_http_url
            QDesktopServices.openUrl(QUrl(validate_http_url(url)))
        except Exception as exc:
            QMessageBox.warning(self, "Unable to open source", str(exc))

    def _update_telemetry(self, sample: dict) -> None:
        self.metric_cards["cpu"].set_metric(sample.get("cpu"))
        memory = sample.get("memory")
        used = sample.get("memory_used")
        total = sample.get("memory_total")
        detail = f"{used:.1f} / {total:.1f} GB  ·  {memory:.0f}%" if memory is not None and used is not None else None
        self.metric_cards["memory"].set_metric(memory, detail)
        self.metric_cards["disk"].set_metric(sample.get("disk"))
        battery = sample.get("battery")
        self.metric_cards["battery"].set_metric(battery, f"{battery:.0f}%" if battery is not None else None)
        temperature = sample.get("temperature")
        self.metric_cards["temperature"].set_metric(min(temperature or 0, 100) if temperature is not None else None, f"{temperature:.1f} °C" if temperature is not None else None)
        import platform
        self.system_platform.setText(f"{platform.platform()}  ·  telemetry refreshed {datetime.now().astimezone().strftime('%H:%M:%S')}")
        self.os_indicator.setText(f"▣  PLATFORM  /  {platform.system().upper()}")
        self.os_indicator.setObjectName("Muted")
        self.os_indicator.style().unpolish(self.os_indicator)
        self.os_indicator.style().polish(self.os_indicator)

    def _start_telemetry(self) -> None:
        self.telemetry = TelemetryWorker(parent=self)
        self.telemetry.sample_ready.connect(self._update_telemetry)
        self.telemetry.error.connect(lambda error: self.system_platform.setText("Telemetry unavailable: " + error))
        self.telemetry.start()

    def _refresh_memories(self, *args) -> None:
        if not hasattr(self, "memory_list"):
            return
        self.memory_list.clear()
        query = self.memory_search.text() if hasattr(self, "memory_search") else ""
        for item in self.memory.list(query):
            row = QListWidgetItem(f"{item['category']}  /  {item['fact_key']}\n{item['fact_value']}\nUpdated {item['updated_at']}")
            row.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.memory_list.addItem(row)
        enabled = self.settings.get("memory_enabled", True)
        self.memory_state_label.setText(f"Memory is {'enabled' if enabled else 'disabled'} for Gemini prompts. Stored facts remain available for review.")

    def _add_memory(self) -> None:
        category, ok = QInputDialog.getText(self, "Add approved fact", "Category (e.g. Preference, Project):")
        if not ok:
            return
        key, ok = QInputDialog.getText(self, "Add approved fact", "Fact name:")
        if not ok:
            return
        value, ok = QInputDialog.getMultiLineText(self, "Add approved fact", "Fact value:")
        if not ok:
            return
        try:
            self.memory.save(category, key, value)
            self._refresh_memories()
        except Exception as exc:
            QMessageBox.warning(self, "Memory was not saved", str(exc))

    def _selected_memory_id(self) -> int | None:
        current = self.memory_list.currentItem()
        return int(current.data(Qt.ItemDataRole.UserRole)) if current else None

    def _edit_selected_memory(self, item=None) -> None:
        memory_id = self._selected_memory_id()
        if memory_id is None:
            return
        selected = next((entry for entry in self.memory.list() if entry["id"] == memory_id), None)
        if not selected:
            return
        category, ok = QInputDialog.getText(self, "Edit approved fact", "Category:", text=selected["category"])
        if not ok:
            return
        value, ok = QInputDialog.getMultiLineText(self, "Edit approved fact", selected["fact_key"] + " value:", selected["fact_value"])
        if ok:
            try:
                self.memory.save(category, selected["fact_key"], value)
                self._refresh_memories()
            except Exception as exc:
                QMessageBox.warning(self, "Memory was not updated", str(exc))

    def _delete_selected_memory(self) -> None:
        memory_id = self._selected_memory_id()
        if memory_id is None:
            return
        if QMessageBox.question(self, "Delete saved fact?", "This removes the selected memory fact permanently.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.memory.delete(memory_id)
            self._refresh_memories()

    def _erase_memories(self) -> None:
        if QMessageBox.question(self, "Erase all saved memories?", "This permanently deletes every long-term memory fact. Conversation history is not affected.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.memory.erase_all()
            self._refresh_memories()

    def _update_credential_status(self) -> None:
        configured = bool(get_api_key())
        message = "Gemini credential available in OS keychain or environment." if configured else "No Gemini credential found. Add one above to use real text and voice sessions."
        if hasattr(self, "credential_status"):
            self.credential_status.setText(message)
        if hasattr(self, "gemini_indicator"):
            self.gemini_indicator.setText("●  GEMINI  /  CONFIGURED" if configured else "◌  GEMINI  /  NOT CONFIGURED")
            self.gemini_indicator.setStyleSheet("color:#71d7be" if configured else "color:#73909d")
        if hasattr(self, "memory_indicator"):
            self.memory_indicator.setText("◈  MEMORY  /  " + ("ON" if self.settings.get("memory_enabled", True) else "OFF"))

    def _save_key(self) -> None:
        try:
            save_api_key(self.api_key_input.text())
            self.api_key_input.clear()
            self._update_credential_status()
            self.status_line.setText("Gemini API key saved in the OS credential store. The key is not displayed or logged.")
        except Exception as exc:
            QMessageBox.warning(self, "Key was not saved", str(exc))

    def _delete_key(self) -> None:
        if QMessageBox.question(self, "Remove saved Gemini key?", "This deletes the key from the OS credential store. An environment variable fallback may still be present.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                delete_api_key()
                self._update_credential_status()
            except Exception as exc:
                QMessageBox.warning(self, "Key was not removed", str(exc))

    def _refresh_roots(self) -> None:
        self.root_list.clear()
        for root in self.settings.get("approved_roots", []):
            self.root_list.addItem(root)

    def _add_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose a folder for approved file access")
        if not selected:
            return
        path = str(Path(selected).expanduser().resolve())
        roots = self.settings.get("approved_roots", [])
        if path not in roots:
            roots.append(path)
            self.settings.set("approved_roots", roots)
            self._refresh_roots()

    def _remove_root(self) -> None:
        item = self.root_list.currentItem()
        if item:
            roots = [root for root in self.settings.get("approved_roots", []) if root != item.text()]
            self.settings.set("approved_roots", roots)
            self._refresh_roots()

    def _refresh_plugins(self) -> None:
        if not hasattr(self, "plugin_list"):
            return
        self.plugin_list.clear()
        enabled = set(self.settings.get("enabled_plugins", []))
        outcomes = dict(self.plugin_results)
        for name in self.plugin_manager.discover():
            status = outcomes.get(name, "enabled after restart" if name in enabled else "disabled")
            item = QListWidgetItem(f"{name}  ·  {status}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(status)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in enabled else Qt.CheckState.Unchecked)
            self.plugin_list.addItem(item)

    def _save_settings(self) -> None:
        text_model, live_model = self.text_model_input.text().strip(), self.live_model_input.text().strip()
        if not text_model or not live_model:
            QMessageBox.warning(self, "Settings not saved", "Both Gemini model names are required.")
            return
        self.settings.set("text_model", text_model)
        self.settings.set("live_model", live_model)
        self.settings.set("voice", self.voice_combo.currentText())
        self.settings.set("memory_enabled", self.memory_enabled.isChecked())
        self.settings.set("input_device", self.input_device_combo.currentData())
        self.settings.set("output_device", self.output_device_combo.currentData())
        enabled_plugins = []
        for index in range(self.plugin_list.count()):
            item = self.plugin_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                enabled_plugins.append(item.data(Qt.ItemDataRole.UserRole))
        self.settings.set("enabled_plugins", enabled_plugins)
        self.memory_indicator.setText("◈  MEMORY  /  " + ("ON" if self.settings.get("memory_enabled") else "OFF"))
        self._update_credential_status()
        self.status_line.setText("Settings saved. Plugin changes take effect after restart.")

    def _refresh_audio_devices(self) -> None:
        self.input_device_combo.clear()
        self.output_device_combo.clear()
        self.input_device_combo.addItem("System default", None)
        self.output_device_combo.addItem("System default", None)
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for _, device in enumerate(devices):
                host = sd.query_hostapis(int(device["hostapi"]))["name"]
                key = f"{device['name']}|||{host}"
                label = f"{device['name']}  ·  {host}"
                if int(device["max_input_channels"]) > 0:
                    self.input_device_combo.addItem(label, key)
                if int(device["max_output_channels"]) > 0:
                    self.output_device_combo.addItem(label, key)
            self.audio_device_status.setText("Audio devices listed from PortAudio. Compatibility is checked when Live Voice connects.")
        except Exception as exc:
            self.audio_device_status.setText("Audio device list unavailable: " + str(exc).splitlines()[0][:160])
        for combo, setting_name in [
            (self.input_device_combo, "input_device"),
            (self.output_device_combo, "output_device"),
        ]:
            selected = self.settings.get(setting_name)
            for index in range(combo.count()):
                if combo.itemData(index) == selected:
                    combo.setCurrentIndex(index)
                    break

    def _refresh_activity(self) -> None:
        if not hasattr(self, "activity_layout"):
            return
        self._clear_layout(self.activity_layout)
        records = self.database.actions(150)
        if not records:
            self.activity_layout.addWidget(QLabel("No tool actions have been recorded yet."))
        for action in records:
            card = panel()
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 8, 12, 8)
            at = action["created_at"]
            try:
                at = datetime.fromisoformat(at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            summary = QLabel(f"{at}   ·   {action['tool_name']}\n{action['summary']}")
            summary.setWordWrap(True)
            summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row.addWidget(summary, 1)
            if action["undone"]:
                badge = QLabel("UNDONE")
                badge.setStyleSheet("color:#7fc5a8")
                row.addWidget(badge)
            elif action["reversible"]:
                undo = QPushButton("UNDO")
                undo.clicked.connect(lambda checked=False, action_id=action["id"]: self._undo_action(action_id))
                row.addWidget(undo)
            else:
                badge = QLabel("NO UNDO")
                badge.setObjectName("Muted")
                row.addWidget(badge)
            self.activity_layout.addWidget(card)

    def _undo_action(self, action_id: int) -> None:
        try:
            message = self.tools.undo(action_id)
            QMessageBox.information(self, "Action reversed", message)
        except Exception as exc:
            QMessageBox.warning(self, "Undo stopped safely", str(exc))
        self._refresh_activity()

    def _start_reminder_timer(self) -> None:
        from PyQt6.QtCore import QTimer

        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start(30000)

    def _check_reminders(self) -> None:
        due = self.database.due_reminders(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        for reminder in due:
            message = f"Reminder: {reminder['title']}"
            self.status_line.setText(message)
            try:
                from plyer import notification
                notification.notify(title="Zyvarnth reminder", message=reminder["title"], timeout=10)
            except Exception:
                QMessageBox.information(self, "Zyvarnth reminder", reminder["title"])

    def _toggle_compact(self, enabled: bool) -> None:
        self.settings.set("compact_mode", bool(enabled))
        if hasattr(self, "chat_secondary"):
            self.chat_secondary.setVisible(not enabled)
        self.sidebar.setFixedWidth(168 if enabled else 218)
        if enabled and not self._fullscreen:
            self.resize(1040, 760)
        elif not self._fullscreen:
            self.resize(1440, 920)

    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.showFullScreen()
            self.fullscreen_button.setText("⛶  EXIT IMMERSIVE")
        else:
            self.showNormal()
            self.fullscreen_button.setText("⛶  IMMERSIVE")

    def emergency_stop(self) -> None:
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.cancel()
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.cancel()
        if self.single_tool_worker and self.single_tool_worker.isRunning():
            self.single_tool_worker.cancel()
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop()
        self.ptt_button.setEnabled(False)
        self.status_line.setText("Emergency stop sent to active requests, tasks, and voice capture.")

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                MainWindow._clear_layout(item.layout())

    def closeEvent(self, event) -> None:
        self.emergency_stop()
        if self.telemetry:
            self.telemetry.stop()
        for worker in [self.chat_worker, self.task_worker, self.single_tool_worker, self.voice_worker, self.telemetry, self.search_worker, self.screenshot_worker]:
            if worker and worker.isRunning():
                worker.wait(1800)
        event.accept()

