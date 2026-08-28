"""Reusable widgets used by the main window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget


class ProgressCell(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.bar.setAlignment(Qt.AlignCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self.bar)

    def set_value(self, value):
        self.bar.setValue(max(0, min(100, int(value or 0))))

    def value(self):
        return self.bar.value()


class RowActions(QWidget):
    def __init__(self, on_start, on_retry, on_cancel, on_open, on_remove=None, parent=None):
        super().__init__(parent)
        self.start = QPushButton("Start")
        self.retry = QPushButton("Retry")
        self.cancel = QPushButton("Cancel")
        self.open_folder = QPushButton("Folder")
        self.remove = QPushButton("Remove")
        self.start.clicked.connect(on_start)
        self.retry.clicked.connect(on_retry)
        self.cancel.clicked.connect(on_cancel)
        self.open_folder.clicked.connect(on_open)
        if on_remove is not None:
            self.remove.clicked.connect(on_remove)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        for button in (self.start, self.retry, self.cancel, self.open_folder, self.remove):
            layout.addWidget(button)
