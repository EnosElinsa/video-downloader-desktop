"""Small, dependency-free Qt styles for the desktop shell."""

from PySide6.QtGui import QFont


COLORS = {
    "dark": {"bg": "#111318", "panel": "#1a1d24", "text": "#f4f6fb", "muted": "#9ba3b4", "accent": "#6ea8fe", "border": "#303641", "danger": "#ef8f8f"},
    "light": {"bg": "#f4f6fa", "panel": "#ffffff", "text": "#18202c", "muted": "#647084", "accent": "#2563eb", "border": "#d9dee8", "danger": "#b42318"},
}


def stylesheet(mode: str = "dark") -> str:
    c = COLORS.get(mode, COLORS["dark"])
    return f"""
    QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: 'Segoe UI'; font-size: 10pt; }}
    QMainWindow {{ background: {c['bg']}; }}
    QFrame#panel, QGroupBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QLineEdit, QTextEdit, QComboBox, QTableWidget {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 6px 8px; selection-background-color: {c['accent']}; }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QTableWidget:focus {{ border: 1px solid {c['accent']}; }}
    QPushButton {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 7px 13px; min-height: 28px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:pressed {{ background: {c['accent']}; color: white; }}
    QPushButton#primaryButton {{ background: {c['accent']}; border-color: {c['accent']}; color: white; font-weight: 600; }}
    QPushButton#dangerButton {{ color: {c['danger']}; }}
    QHeaderView::section {{ background: {c['panel']}; color: {c['muted']}; border: 0; border-bottom: 1px solid {c['border']}; padding: 7px; font-weight: 600; }}
    QProgressBar {{ background: {c['border']}; border: 0; border-radius: 4px; text-align: center; color: {c['text']}; min-height: 10px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
    QPlainTextEdit {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 7px; }}
    QLabel#muted {{ color: {c['muted']}; }}
    """


def app_font(point_size: int = 10, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont("Segoe UI")
    font.setPointSize(point_size)
    font.setWeight(QFont.Weight(weight))
    return font
