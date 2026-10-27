from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QPoint, QEvent, QRect
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QHeaderView, QApplication
)
from PySide6.QtGui import QColor

from beamerplus.PdfReader import PdfReader


class BookmarkDrawer(QFrame):
    """PDFのしおり（目次/TOC）を用いてページを素早く移動するための
    左側引き出しオーバーレイウィジェット。
    影や半透明を使わず、不透明な背景（#252526）を確実に描画して高視認性を確保。"""

    page_selected = Signal(int)
    drawer_state_changed = Signal(bool)

    PANEL_WIDTH = 300

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.is_open: bool = False
        self.has_bookmarks: bool = False
        self.current_page_idx: int = 0
        self.sidebar_offset: int = 0
        self.trigger_widget: QWidget | None = None
        self._suppress_next_release: bool = False

        self.setFixedWidth(self.PANEL_WIDTH)
        self.setObjectName("BookmarkDrawer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#BookmarkDrawer {"
            "  background-color: #252526;"
            "  border-right: 2px solid #3e3e42;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ヘッダー領域（しまう用ボタンは置かず、タイトルのみ表示）
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel("📑 しおり / 目次")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(lbl_title)
        layout.addLayout(header_layout)

        # 検索バー
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 しおりを検索...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit {"
            "  background-color: #1e1e1e;"
            "  color: #ffffff;"
            "  border: 1px solid #3e3e42;"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "  font-size: 12px;"
            "}"
            "QLineEdit:focus { border-color: #007acc; }"
        )
        self.search_edit.textChanged.connect(self._filter_tree)
        layout.addWidget(self.search_edit)

        # ツリーウィジェット
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setStyleSheet(
            "QTreeWidget {"
            "  background-color: #1e1e1e;"
            "  color: #cccccc;"
            "  border: 1px solid #3e3e42;"
            "  border-radius: 4px;"
            "  outline: none;"
            "  font-size: 12px;"
            "}"
            "QTreeWidget::item { padding: 4px 2px; border-radius: 3px; }"
            "QTreeWidget::item:hover { background-color: #2a2d32; color: #ffffff; }"
            "QTreeWidget::item:selected { background-color: #094771; color: #ffffff; font-weight: bold; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 8px; }"
            "QScrollBar::handle:vertical { background: #3e3e42; border-radius: 4px; min-height: 20px; }"
            "QScrollBar::handle:vertical:hover { background: #505054; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        
        # 列幅設定（名前側を最大限広くし、ページ番号列は右端にコンパクトな固定幅）
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 52)

        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

        # アニメーション初期化（機敏な150ms）
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self._on_animation_finished)

        # 親イベントの監視設定
        if parent:
            parent.installEventFilter(self)

        # 初期状態は非表示（PDF未ロード状態）
        self.hide()

    def set_trigger_widget(self, widget: QWidget):
        """左端の引き出しボタン（トリガーウィジェット）を登録"""
        self.trigger_widget = widget

    def set_sidebar_offset(self, offset: int):
        """引き出しボタンの幅によるオフセットを設定"""
        self.sidebar_offset = offset
        self.update_layout()

    def update_layout(self):
        """親ウィジェットの高さに合わせて自身の高さを調整"""
        if not self.parent():
            return
        h = self.parent().height()
        self.setFixedHeight(h)

        # 開閉状態に応じたX位置
        target_x = self.sidebar_offset if self.is_open else (-self.PANEL_WIDTH - 20)
        if not self.animation.state() == QPropertyAnimation.State.Running:
            self.move(target_x, 0)

    def load_pdf(self, reader: PdfReader | None):
        """PDFリーダーからしおりデータを読み込み、UIを構築"""
        self.tree.clear()
        self.search_edit.clear()

        if not reader or not reader.has_toc:
            self.has_bookmarks = False
            self.is_open = False
            self.hide()
            self.drawer_state_changed.emit(False)
            return

        self.has_bookmarks = True
        self._populate_tree(reader.toc)

        # 初期状態は折りたたんで非表示
        self.is_open = False
        self.drawer_state_changed.emit(False)
        self.update_layout()
        self.hide()

    def _populate_tree(self, toc_items: list[tuple[int, str, int]]):
        """スタック構造を用いて階層ツリーを構築"""
        self.tree.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []

        for lvl, title, page_idx in toc_items:
            item = QTreeWidgetItem([title, f"P. {page_idx + 1}"])
            item.setData(0, Qt.ItemDataRole.UserRole, page_idx)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setForeground(1, QColor("#888888"))
            item.setToolTip(0, f"{title} (ページ {page_idx + 1})")

            # 現在の深さ以上のスタックをポップして適切な親を特定
            while stack and stack[-1][0] >= lvl:
                stack.pop()

            if stack:
                stack[-1][1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)

            stack.append((lvl, item))

        self.tree.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        if page_idx is not None and isinstance(page_idx, int):
            self.page_selected.emit(page_idx)
            # ページ選択後はスムーズに閉じる
            self.close_drawer()

    def highlight_current_page(self, current_page_idx: int):
        """現在表示されているページに対応する（直近の）しおり項目をハイライト"""
        self.current_page_idx = current_page_idx
        if not self.has_bookmarks:
            return

        best_item = None
        best_page = -1

        def traverse(item: QTreeWidgetItem):
            nonlocal best_item, best_page
            p = item.data(0, Qt.ItemDataRole.UserRole)
            if p is not None and isinstance(p, int):
                if p <= current_page_idx and p >= best_page:
                    best_page = p
                    best_item = item
            for i in range(item.childCount()):
                traverse(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            traverse(self.tree.topLevelItem(i))

        if best_item:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(best_item)
            self.tree.scrollToItem(best_item)
            self.tree.blockSignals(False)

    def _filter_tree(self, text: str):
        """検索ワードによるツリー項目のリアルタイム絞り込み"""
        q = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            title = item.text(0).lower()
            matched = (q in title) if q else True
            child_matched = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_matched = True

            visible = matched or child_matched
            item.setHidden(not visible)
            if visible and q:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def toggle_drawer(self):
        if not self.has_bookmarks:
            return
        if self.is_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):
        if not self.has_bookmarks or self.is_open:
            return
        self.is_open = True
        self.drawer_state_changed.emit(True)
        self.show()
        self.raise_()
        self._animate_to(self.sidebar_offset)
        self.search_edit.setFocus()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def close_drawer(self):
        if not self.has_bookmarks or not self.is_open:
            return
        self.is_open = False
        self.drawer_state_changed.emit(False)
        self._animate_to(-self.PANEL_WIDTH - 20)
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def _on_animation_finished(self):
        """アニメーション終了時のクリーンアップ処理（完全非表示＆即時再描画）"""
        if not self.is_open:
            self.hide()
            if self.parent():
                self.parent().update()

    def _animate_to(self, target_x: int):
        self.animation.stop()
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(QPoint(target_x, 0))
        self.animation.start()

    def eventFilter(self, watched, event: QEvent) -> bool:
        """親ウィジェットのリサイズ追従、外側クリック検知（スライド進行の抑制）、およびEscキー処理"""
        if watched == self.parent() and event.type() == QEvent.Type.Resize:
            self.update_layout()
            return False

        if self.is_open:
            if event.type() == QEvent.Type.MouseButtonPress:
                pos = None
                if hasattr(event, "globalPosition"):
                    pos = event.globalPosition().toPoint()
                elif hasattr(event, "globalPos"):
                    pos = event.globalPos()

                if pos is not None:
                    # 自ウィジェット（オーバーレイ）領域のグローバル矩形
                    global_top_left = self.mapToGlobal(QPoint(0, 0))
                    global_rect = QRect(global_top_left, self.size())

                    # オーバーレイ外をクリックされた場合:
                    # ドロワーを即座にしまい、クリックイベントを消費して背後への伝播を防止
                    if not global_rect.contains(pos):
                        self._suppress_next_release = True
                        self.close_drawer()
                        return True

            elif event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self.close_drawer()
                    return True

        elif self._suppress_next_release:
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._suppress_next_release = False
                return True

        return super().eventFilter(watched, event)
