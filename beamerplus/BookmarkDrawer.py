from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QPoint, QEvent, QRect
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFrame, QGraphicsDropShadowEffect,
    QHeaderView, QApplication
)
from PySide6.QtGui import QColor

from beamerplus.PdfReader import PdfReader


class BookmarkDrawer(QWidget):
    """PDFのしおり（目次/TOC）を用いてページを素早く移動するための
    左側引き出しオーバーレイウィジェット。"""

    page_selected = Signal(int)

    PANEL_WIDTH = 300
    TAB_WIDTH = 26
    TAB_HEIGHT = 56

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.is_open: bool = False
        self.has_bookmarks: bool = False
        self.current_page_idx: int = 0

        # 全体サイズ設定（パネル部 + 右端の引き出しタブ部）
        self.total_width = self.PANEL_WIDTH + self.TAB_WIDTH
        self.setFixedWidth(self.total_width)

        # 背景全体は透明にし、パネル部分とタブ部分のみ描画
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 1. パネル部分（目次本体コンテナ）
        self.panel = QFrame(self)
        self.panel.setGeometry(0, 0, self.PANEL_WIDTH, self.height())
        self.panel.setStyleSheet(
            "QFrame#BookmarkPanel {"
            "  background-color: #252526;"
            "  border-right: 1px solid #3e3e42;"
            "}"
        )
        self.panel.setObjectName("BookmarkPanel")

        # ドロップシャドウ効果（引き出したときのみ有効化）
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(15)
        self.shadow.setColor(QColor(0, 0, 0, 160))
        self.shadow.setOffset(4, 0)
        self.shadow.setEnabled(False)  # 引き出されていない時は無効化（UIマスク防止）
        self.panel.setGraphicsEffect(self.shadow)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        # ヘッダー領域
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_title = QLabel("📑 しおり / 目次")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(lbl_title)
        
        header_layout.addStretch()

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("閉じる (Esc)")
        self.btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #888888; border: none; font-size: 12px; border-radius: 3px; }"
            "QPushButton:hover { background: #3e3e42; color: #ffffff; }"
        )
        self.btn_close.clicked.connect(self.close_drawer)
        header_layout.addWidget(self.btn_close)
        panel_layout.addLayout(header_layout)

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
        panel_layout.addWidget(self.search_edit)

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
        panel_layout.addWidget(self.tree, 1)

        # 2. 引き出しタブボタン（パネルの右端に突き出る形状、左から引き出せることを示す「>」）
        self.tab_button = QPushButton(">", self)
        self.tab_button.setObjectName("DrawerTabBtn")
        self.tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_button.setToolTip("しおり / 目次を開く (Ctrl+B)")
        self.tab_button.setStyleSheet(
            "QPushButton#DrawerTabBtn {"
            "  background-color: rgba(45, 45, 48, 0.95);"
            "  color: #cccccc;"
            "  border: 1px solid #3e3e42;"
            "  border-left: none;"
            "  border-bottom: none;"
            "  border-top-right-radius: 6px;"
            "  border-bottom-right-radius: 0px;"
            "  font-size: 14px;"
            "  font-weight: bold;"
            "  padding: 0px;"
            "}"
            "QPushButton#DrawerTabBtn:hover {"
            "  background-color: #007acc;"
            "  color: #ffffff;"
            "  border-color: #0098ff;"
            "}"
        )
        self.tab_button.clicked.connect(self.toggle_drawer)

        # アニメーション初期化
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self._on_animation_finished)

        # 親イベントの監視設定
        if parent:
            parent.installEventFilter(self)

        # 初期状態は非表示（PDF未ロード状態）
        self.hide()

    def update_layout(self):
        """親ウィジェットの高さに合わせて自身とパネルの高さを調整し、タブ位置をウィンドウ最下部に配置"""
        h = self.parent().height() if self.parent() else self.height()
        if h <= 0:
            return
        self.setFixedHeight(h)
        self.panel.setGeometry(0, 0, self.PANEL_WIDTH, h)

        # タブボタンの縦位置: ウィンドウ最下部
        tab_y = max(0, h - self.TAB_HEIGHT)
        self.tab_button.setGeometry(self.PANEL_WIDTH, tab_y, self.TAB_WIDTH, self.TAB_HEIGHT)

        # 開閉状態に応じたX位置
        target_x = 0 if self.is_open else -self.PANEL_WIDTH
        if not self.animation.state() == QPropertyAnimation.State.Running:
            self.move(target_x, 0)

    def load_pdf(self, reader: PdfReader | None):
        """PDFリーダーからしおりデータを読み込み、UIを構築"""
        self.tree.clear()
        self.search_edit.clear()

        if not reader or not reader.has_toc:
            self.has_bookmarks = False
            self.hide()
            return

        self.has_bookmarks = True
        self._populate_tree(reader.toc)

        # しおりが存在する場合は初期位置（折りたたまれた状態）で表示
        self.is_open = False
        self.tab_button.setText(">")
        self.tab_button.setToolTip("しおり / 目次を開く (Ctrl+B)")
        self.update_layout()
        self.show()
        self.raise_()

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
            # ページ選択後はプレゼンに集中できるようスムーズに閉じる
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
        self.tab_button.setText("<")
        self.tab_button.setToolTip("しおり / 目次を閉じる (Esc, Ctrl+B)")
        self.shadow.setEnabled(True)  # 引き出したときに影を有効化
        self.raise_()
        self._animate_to(0)
        self.search_edit.setFocus()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def close_drawer(self):
        if not self.has_bookmarks or not self.is_open:
            return
        self.is_open = False
        self.tab_button.setText(">")
        self.tab_button.setToolTip("しおり / 目次を開く (Ctrl+B)")
        self._animate_to(-self.PANEL_WIDTH)
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def _on_animation_finished(self):
        # 完全に閉じた後は影エフェクトを無効化してUIマスクを完全に防止
        if not self.is_open:
            self.shadow.setEnabled(False)

    def _animate_to(self, target_x: int):
        self.animation.stop()
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(QPoint(target_x, 0))
        self.animation.start()

    def mousePressEvent(self, event):
        """引き出されていない時はタブボタン以外の領域をクリックしても背後へイベントを透過"""
        if not self.is_open:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if not self.tab_button.geometry().contains(pos):
                event.ignore()
                return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event: QEvent) -> bool:
        """親ウィジェットのリサイズ追従、外側クリック検知、およびEscキー処理"""
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
                    global_top_left = self.mapToGlobal(QPoint(0, 0))
                    global_rect = QRect(global_top_left, self.size())
                    if not global_rect.contains(pos):
                        self.close_drawer()
                        return False

            elif event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self.close_drawer()
                    return True

        return super().eventFilter(watched, event)
