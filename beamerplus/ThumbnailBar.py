from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout, QLabel, QFrame
)
from PySide6.QtGui import QPixmap, QMouseEvent

from beamerplus.PdfReader import PdfReader


class ThumbnailItem(QFrame):
    clicked = Signal(int)

    def __init__(self, index: int, label_text: str, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self.is_selected = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ThumbnailItem")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.caption_label = QLabel(label_text)
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setStyleSheet("font-size: 11px; color: #d0d0d0;")
        layout.addWidget(self.caption_label)

        self.update_style()

    def set_selected(self, selected: bool):
        if self.is_selected != selected:
            self.is_selected = selected
            self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(
                "#ThumbnailItem { border: 2px solid #007acc; border-radius: 4px; background-color: #2a2d32; }"
            )
            self.caption_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #4fc3f7;")
        else:
            self.setStyleSheet(
                "#ThumbnailItem { border: 2px solid transparent; border-radius: 4px; background-color: transparent; }"
                "#ThumbnailItem:hover { border: 2px solid #555555; background-color: #252526; }"
            )
            self.caption_label.setStyleSheet("font-size: 11px; color: #aaaaaa;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


class ThumbnailBar(QWidget):
    page_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.items: list[ThumbnailItem] = []
        self.current_index: int = 0

        self.setFixedHeight(140)
        self.setStyleSheet("background-color: #1e1e1e;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: #1e1e1e; }"
            "QScrollBar:horizontal { height: 10px; background: #1e1e1e; }"
            "QScrollBar::handle:horizontal { background: #3e3e42; border-radius: 5px; min-width: 20px; }"
            "QScrollBar::handle:horizontal:hover { background: #505054; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
        )

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #1e1e1e;")
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(8, 6, 8, 6)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area)

    def load_pdf(self, reader: PdfReader):
        self.clear()
        target_size = QSize(140, 95)
        for i in range(len(reader)):
            pix = reader.get_page_image(i, auto_crop=True, size=target_size, dpi=72)
            if pix is None:
                continue
            label_text = f"{i + 1}"
            if i < len(reader.page_labels) and reader.page_labels[i]:
                label_text = f"{i + 1} ({reader.page_labels[i]})"
            item = ThumbnailItem(i, label_text, pix)
            item.clicked.connect(self._on_item_clicked)
            self.container_layout.addWidget(item)
            self.items.append(item)

        if self.items:
            self.set_current_page(0)

    def _on_item_clicked(self, index: int):
        self.page_selected.emit(index)

    def set_current_page(self, index: int):
        if not (0 <= index < len(self.items)):
            return
        self.current_index = index
        for i, item in enumerate(self.items):
            item.set_selected(i == index)

        self.ensure_visible(index)

    def ensure_visible(self, index: int):
        if 0 <= index < len(self.items):
            item = self.items[index]
            self.scroll_area.ensureWidgetVisible(item, 50, 0)

    def clear(self):
        self.items.clear()
        while self.container_layout.count() > 0:
            child = self.container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.current_index = 0
