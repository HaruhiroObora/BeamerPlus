from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QHBoxLayout, QVBoxLayout, QLabel, QFrame
)
from PySide6.QtGui import QPixmap, QMouseEvent, QWheelEvent

from beamerplus.PdfReader import PdfReader


class ThumbnailScrollArea(QScrollArea):
    """水平方向に配置されたサムネイル一覧用のスクロールエリア。
    縦方向のマウスホイール回転またはトラックパッドの水平スクロールを検知し、
    水平スクロールバーをスムーズに操作できるようにする。"""

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta != 0:
            sb = self.horizontalScrollBar()
            # 1ノッチ(120)あたり約1枚分(約150px)スムーズにスクロール
            step = int(delta * 1.25)
            sb.setValue(sb.value() - step)
            event.accept()
        else:
            super().wheelEvent(event)


class ThumbnailItem(QFrame):
    clicked = Signal(int)

    def __init__(
        self,
        group_index: int,
        page_indices: list[int],
        base_label: str,
        pixmap: QPixmap,
        parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.group_index = group_index
        self.page_indices = page_indices
        self.base_label = base_label
        self.is_selected = False
        self.has_multiple_pages = len(page_indices) > 1

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ThumbnailItem")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.caption_label = QLabel()
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.caption_label)

        self._update_caption(current_page_idx=None)
        self.update_style()

    def _update_caption(self, current_page_idx: int | None = None):
        if not self.has_multiple_pages:
            self.caption_label.setText(self.base_label)
            return

        total_sub = len(self.page_indices)
        if current_page_idx is not None and current_page_idx in self.page_indices:
            sub_idx = self.page_indices.index(current_page_idx) + 1
            self.caption_label.setText(f"{self.base_label} ({sub_idx}/{total_sub})")
        else:
            self.caption_label.setText(f"{self.base_label} ({total_sub}枚)")

    def set_selected(self, selected: bool, current_page_idx: int | None = None):
        state_changed = (self.is_selected != selected)
        self.is_selected = selected
        self._update_caption(current_page_idx if selected else None)
        if state_changed or selected:
            self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(
                "#ThumbnailItem { border: 2px solid #007acc; border-radius: 4px; background-color: #2a2d32; }"
            )
            self.caption_label.setStyleSheet("font-size: 11px; color: #4fc3f7; font-weight: bold;")
        else:
            self.setStyleSheet(
                "#ThumbnailItem { border: 2px solid transparent; border-radius: 4px; background-color: transparent; }"
                "#ThumbnailItem:hover { border: 2px solid #555555; background-color: #252526; }"
            )
            self.caption_label.setStyleSheet("font-size: 11px; color: #aaaaaa;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # 先頭サブページ（グループの開始ページ）へ遷移
            self.clicked.emit(self.page_indices[0])
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

        self.scroll_area = ThumbnailScrollArea(self)
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

        # スクロールエリアとコンテナにイベントフィルタを設定（ホイール操作を確実に補足）
        self.scroll_area.viewport().installEventFilter(self)
        self.container.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            self.scroll_area.wheelEvent(event)
            return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event: QWheelEvent):
        # バー本体領域でのホイール操作もスクロールエリアに転送
        self.scroll_area.wheelEvent(event)

    def load_pdf(self, reader: PdfReader):
        self.clear()
        target_size = QSize(140, 95)
        for group in reader.page_groups:
            # 代表サムネイル画像は完全な内容が表示されているグループの最終サブページ
            rep_page_idx = group.page_indices[-1]
            pix = reader.get_page_image(rep_page_idx, auto_crop=True, size=target_size, dpi=72)
            if pix is None:
                continue

            base_lbl = group.label if group.label else str(group.page_indices[0] + 1)
            item = ThumbnailItem(
                group_index=group.group_index,
                page_indices=group.page_indices,
                base_label=base_lbl,
                pixmap=pix
            )
            item.clicked.connect(self._on_item_clicked)

            # サムネイルアイテム及びその内部ラベル上でもホイールイベントを確実に拾う
            item.installEventFilter(self)
            item.image_label.installEventFilter(self)
            item.caption_label.installEventFilter(self)

            self.container_layout.addWidget(item)
            self.items.append(item)

        if self.items:
            self.set_current_page(0)

    def _on_item_clicked(self, index: int):
        self.page_selected.emit(index)

    def set_current_page(self, index: int):
        self.current_index = index
        matched_item = None
        for item in self.items:
            is_match = (index in item.page_indices)
            item.set_selected(is_match, current_page_idx=index)
            if is_match:
                matched_item = item

        if matched_item:
            self.scroll_area.ensureWidgetVisible(matched_item, 50, 0)

    def ensure_visible(self, index: int):
        for item in self.items:
            if index in item.page_indices:
                self.scroll_area.ensureWidgetVisible(item, 50, 0)
                break

    def clear(self):
        self.items.clear()
        while self.container_layout.count() > 0:
            child = self.container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.current_index = 0
