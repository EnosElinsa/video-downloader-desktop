"""Fluent-inspired palette and typography for the desktop shell."""
from PySide6.QtGui import QFont

COLORS = {
    "dark": {"bg":"#0B0E14","surface":"#121722","surface2":"#181E2B","border":"#283142","text":"#F5F7FB","muted":"#8F9AAD","accent":"#7C5CFC","accent_hover":"#8B70FF","success":"#39C887","warning":"#F3B95F","error":"#F06A75"},
    "light": {"bg":"#F7F9FC","surface":"#FFFFFF","surface2":"#F0F3F9","border":"#D9E0EC","text":"#182133","muted":"#647084","accent":"#6750D9","accent_hover":"#5640C5","success":"#178A5B","warning":"#A86B13","error":"#B4233A"},
}

def stylesheet(mode: str = "dark") -> str:
    c = COLORS.get(mode, COLORS["dark"])
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 10pt; }}
    QMainWindow, QDialog, QWidget#mainRoot, QWidget#contentRoot {{ background: {c['bg']}; }}
    QLabel {{ background: transparent; border: 0; }}
    QCheckBox, QDialogButtonBox, QWidget#queueList, QWidget#emptyState, QWidget#settingsOutputRow {{ background: transparent; border: 0; }}
    QFrame#appHeader {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    QFrame#composer, QFrame#downloadCard, QFrame#activityDrawer, QGroupBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    QFrame#downloadCard {{ border-radius: 10px; }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 10px; selection-background-color: {c['accent']}; min-height: 20px; }}
    QPlainTextEdit {{ padding: 10px; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {c['accent']}; }}
    QComboBox {{ padding-right: 38px; }}
    QComboBox::drop-down {{ subcontrol-origin: border; subcontrol-position: top right; width: 34px; background: {c['surface2']}; border-left: 1px solid {c['border']}; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; selection-background-color: {c['accent']}; outline: 0; }}
    QSpinBox {{ padding-right: 38px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 30px; background: {c['surface2']}; border-left: 1px solid {c['border']}; }}
    QSpinBox::up-button {{ subcontrol-position: top right; border-bottom: 1px solid {c['border']}; border-top-right-radius: 8px; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 8px; }}
    QPushButton {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 14px; min-height: 30px; }}
    QPushButton:hover {{ border-color: {c['accent_hover']}; }} QPushButton:pressed {{ background: {c['accent']}; color: white; }}
    QPushButton#addToQueueButton, QPushButton#primaryButton {{ background: {c['accent']}; border-color: {c['accent']}; color: white; font-weight: 600; }}
    QPushButton#addToQueueButton:hover, QPushButton#primaryButton:hover {{ background: {c['accent_hover']}; }}
    QPushButton#iconButton {{ padding: 5px; min-width: 30px; min-height: 30px; }}
    QLabel#muted, QLabel#cardMeta, QLabel#latestActivity {{ color: {c['muted']}; }} QLabel#pageTitle {{ font-size: 20pt; font-weight: 700; }} QLabel#sectionTitle {{ font-size: 11pt; font-weight: 600; }}
    QLabel#statusRunning {{ color: {c['accent_hover']}; font-weight: 600; }} QLabel#statusSuccess {{ color: {c['success']}; font-weight: 600; }} QLabel#statusFailed {{ color: {c['error']}; font-weight: 600; }} QLabel#statusCancelled {{ color: {c['warning']}; }}
    QProgressBar {{ background: {c['surface2']}; border: 0; border-radius: 4px; text-align: center; color: {c['text']}; min-height: 9px; max-height: 9px; }} QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ border: 0; background: transparent; }} QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }} QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 28px; }} QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }} QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QGroupBox {{ margin-top: 12px; padding: 16px 12px 12px; font-weight: 600; }} QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
    """

def app_font(point_size: int = 10, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont("Segoe UI Variable")
    if not font.exactMatch(): font = QFont("Segoe UI")
    font.setPointSize(point_size); font.setWeight(QFont.Weight(weight)); return font
