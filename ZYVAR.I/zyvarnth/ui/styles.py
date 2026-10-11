STYLESHEET = r"""
QWidget { background: #080d13; color: #d7e5ed; font-family: 'Inter', 'SF Pro Display', 'Segoe UI', sans-serif; font-size: 13px; }
QLabel { background: transparent; }
QMainWindow { background: #080d13; }
QFrame#Sidebar { background: #0a1119; border-right: 1px solid #172733; }
QFrame#TopBar { background: #0b131b; border-bottom: 1px solid #1c303b; }
QFrame#Panel, QFrame#Card { background: #0d1720; border: 1px solid #1b303d; border-radius: 12px; }
QLabel#Brand { color: #e8f6fc; font-size: 18px; font-weight: 700; letter-spacing: 2px; }
QLabel#Eyebrow { color: #5f93a6; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#PageTitle { color: #e3f3f9; font-size: 20px; font-weight: 600; }
QLabel#Muted { color: #73909d; }
QLabel#Value { color: #a9edf9; font-size: 22px; font-weight: 600; }
QPushButton, QToolButton { background: #12232d; color: #b9d2dc; border: 1px solid #23404c; border-radius: 8px; padding: 9px 12px; }
QPushButton:hover, QToolButton:hover { background: #17303c; border-color: #30b9d2; color: #e5fbff; }
QPushButton:pressed, QToolButton:pressed { background: #174454; }
QPushButton#Primary { background: #0b829c; border: 1px solid #20bed5; color: #f2fcff; font-weight: 700; }
QPushButton#Primary:hover { background: #0e9ab4; }
QPushButton#Danger { background: #35171d; border: 1px solid #75313b; color: #ffadb3; }
QPushButton#Nav { background: transparent; border: 1px solid transparent; text-align: left; padding: 11px 12px; color: #7895a3; }
QPushButton#Nav:hover { background: #10212b; color: #d2f7ff; }
QPushButton#Nav:checked { background: #102832; color: #80e6f4; border: 1px solid #235464; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget { background: #09121a; color: #d7e5ed; border: 1px solid #203541; border-radius: 8px; padding: 9px; selection-background-color: #176477; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #27aabe; }
QComboBox QAbstractItemView { background: #0d1720; color: #d7e5ed; selection-background-color: #164b5b; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #274451; border-radius: 4px; min-height: 24px; }
QProgressBar { background: #101d27; border: none; border-radius: 4px; height: 7px; text-align: center; }
QProgressBar::chunk { background: #2dbbd0; border-radius: 4px; }
QCheckBox { spacing: 8px; color: #b3c8d0; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked { border: 1px solid #42616d; border-radius: 4px; background: #0a141b; }
QCheckBox::indicator:checked { border: 1px solid #22b4c9; border-radius: 4px; background: #0d788d; }
QToolTip { background: #132832; color: #e0f8fd; border: 1px solid #2a6777; padding: 5px; }
"""

