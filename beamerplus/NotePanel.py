from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit,
    QPlainTextEdit, QLabel, QPushButton, QStackedWidget, QFrame, QScrollArea
)
from PySide6.QtGui import QPixmap, QFont, QResizeEvent

from beamerplus.PdfReader import PdfReader


class NotePanel(QWidget):
    """
    発表者画面のサイドに配置されるノートパネル
    （次のスライドプレビュー ＋ Markdown形式ノートの閲覧・編集 ＋ Beamer埋め込みノートの表示）
    デフォルトはプレビューモードで表示され、「✏️ 編集」ボタンで直接編集可能。
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.pdf_reader: PdfReader | None = None
        self.active_page_index: int = 0
        self._current_note_pixmap: QPixmap | None = None

        # 自動保存タイマー
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self._auto_save_to_file)

        self.setMinimumWidth(280)
        self.setStyleSheet("background-color: #202023;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 上部パネルヘッダー
        panel_header = QFrame()
        panel_header.setFixedHeight(38)
        panel_header.setStyleSheet("background-color: #28282b; border-bottom: 1px solid #38383c;")
        ph_layout = QHBoxLayout(panel_header)
        ph_layout.setContentsMargins(12, 0, 10, 0)

        self.lbl_title = QLabel("📝 スライドノート")
        self.lbl_title.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        ph_layout.addWidget(self.lbl_title)
        ph_layout.addStretch()

        self.save_status_label = QLabel("")
        self.save_status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
        ph_layout.addWidget(self.save_status_label)

        main_layout.addWidget(panel_header)

        # 内部スプリッター（上下: 次のスライドプレビュー & Markdownエディタ）
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background-color: #333336; height: 3px; }"
        )

        # --- 1. 次のスライドプレビューエリア ---
        next_slide_widget = QWidget()
        next_layout = QVBoxLayout(next_slide_widget)
        next_layout.setContentsMargins(8, 8, 8, 8)
        next_layout.setSpacing(4)

        next_header = QLabel("次のスライド")
        next_header.setStyleSheet("color: #888888; font-size: 11px;")
        next_layout.addWidget(next_header)

        self.next_slide_image = QLabel()
        self.next_slide_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_slide_image.setStyleSheet(
            "background-color: #161618; border: 1px solid #333336; border-radius: 4px;"
        )
        next_layout.addWidget(self.next_slide_image, 1)

        self.splitter.addWidget(next_slide_widget)

        # --- 2. Markdownノート表示・編集エリア ---
        note_widget = QWidget()
        note_layout = QVBoxLayout(note_widget)
        note_layout.setContentsMargins(8, 6, 8, 8)
        note_layout.setSpacing(6)

        # エディタ操作ツールバー
        tb_layout = QHBoxLayout()
        self.lbl_page_note = QLabel("スライド 1")
        self.lbl_page_note.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        tb_layout.addWidget(self.lbl_page_note)
        tb_layout.addStretch()

        # PDF埋め込みノート画面表示ボタン（2画面レイアウト時）
        self.btn_pdf_note_view = QPushButton("📄 PDFノート画面")
        self.btn_pdf_note_view.setCheckable(True)
        self.btn_pdf_note_view.setStyleSheet(self._btn_style())
        self.btn_pdf_note_view.setToolTip("LaTeX Beamerで組版されたPDFノート画面を表示（もう一度クリックでメモに戻る）")
        self.btn_pdf_note_view.clicked.connect(self._toggle_pdf_note_view)
        self.btn_pdf_note_view.setVisible(False)
        tb_layout.addWidget(self.btn_pdf_note_view)

        self.btn_edit = QPushButton("✏️ 編集")
        self.btn_edit.setCheckable(True)
        self.btn_edit.setChecked(False)  # デフォルトはプレビューモード（未選択）
        self.btn_edit.setToolTip("ノートを編集する（もう一度クリックでプレビューに戻る）")
        self.btn_edit.setStyleSheet(self._btn_style())
        self.btn_edit.clicked.connect(self._toggle_edit_mode)
        tb_layout.addWidget(self.btn_edit)

        for btn in (self.btn_pdf_note_view, self.btn_edit):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        note_layout.addLayout(tb_layout)

        # スタックウィジェット (index 0: 編集, index 1: プレビュー, index 2: PDFノートスライド画面)
        self.note_stack = QStackedWidget()

        # エディタ (index 0)
        self.editor = QPlainTextEdit()
        font = QFont("Monospace", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.setPlaceholderText("このスライドに関するメモ・発表原稿をMarkdown形式で記述...")
        self.editor.setStyleSheet(
            "QPlainTextEdit { background-color: #18181a; color: #d4d4d4; border: 1px solid #38383c; border-radius: 4px; padding: 6px; selection-background-color: #264f78; }"
        )
        self.editor.textChanged.connect(self._on_note_text_changed)
        self.note_stack.addWidget(self.editor)

        # プレビュー（デフォルト表示, index 1）
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            "QTextEdit { background-color: #18181a; color: #e0e0e0; border: 1px solid #38383c; border-radius: 4px; padding: 8px; }"
        )
        self.note_stack.addWidget(self.preview)

        # PDFノートスライド画面表示 (index 2)
        self.note_scroll_area = QScrollArea()
        self.note_scroll_area.setWidgetResizable(True)
        self.note_scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #38383c; background-color: #18181a; }"
        )
        self.note_image_container = QWidget()
        self.note_image_container.setStyleSheet("background-color: #18181a;")
        nic_layout = QVBoxLayout(self.note_image_container)
        nic_layout.setContentsMargins(4, 4, 4, 4)
        self.lbl_pdf_note_image = QLabel()
        self.lbl_pdf_note_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nic_layout.addWidget(self.lbl_pdf_note_image)
        self.note_scroll_area.setWidget(self.note_image_container)
        self.note_stack.addWidget(self.note_scroll_area)

        # デフォルトはプレビューモード (index 1)
        self.note_stack.setCurrentIndex(1)

        note_layout.addWidget(self.note_stack, 1)
        self.splitter.addWidget(note_widget)

        # スプリッターの比率設定 (プレビュー: 30%, ノート: 70%)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)

        main_layout.addWidget(self.splitter, 1)

    def _btn_style(self) -> str:
        return (
            "QPushButton { background-color: #333336; color: #ffffff; border: 1px solid #444448; border-radius: 3px; padding: 3px 10px; font-size: 11px; }"
            "QPushButton:hover { background-color: #44444a; }"
            "QPushButton:checked { background-color: #007acc; border-color: #0098ff; }"
        )

    def _toggle_edit_mode(self):
        """有効になっている機能のボタンをクリックしたらプレビューモード（デフォルト）に戻る"""
        if self.btn_edit.isChecked():
            # 編集モードへ
            self.btn_pdf_note_view.setChecked(False)
            self.note_stack.setCurrentIndex(0)
            self.editor.setFocus()
        else:
            # プレビューモード（デフォルト）へ戻る
            self.save_current_note_to_memory()
            md_text = self.editor.toPlainText()
            self._render_preview(md_text)
            self.note_stack.setCurrentIndex(1)

    def _toggle_pdf_note_view(self):
        """PDFノート画面の表示切り替え（もう一度クリックでプレビューに戻る）"""
        if self.btn_pdf_note_view.isChecked():
            self.btn_edit.setChecked(False)
            self.save_current_note_to_memory()
            self._update_pdf_note_image_display()
            self.note_stack.setCurrentIndex(2)
        else:
            user_text = self.editor.toPlainText()
            self._render_preview(user_text)
            self.note_stack.setCurrentIndex(1)

    def _update_pdf_note_image_display(self):
        if self._current_note_pixmap and not self._current_note_pixmap.isNull():
            target_w = max(240, self.note_scroll_area.viewport().width() - 16)
            scaled = self._current_note_pixmap.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
            self.lbl_pdf_note_image.setPixmap(scaled)
        else:
            self.lbl_pdf_note_image.clear()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.note_stack.currentIndex() == 2:
            self._update_pdf_note_image_display()

    def _render_preview(self, md_text: str):
        if md_text.strip():
            self.preview.setMarkdown(md_text)
        elif self.pdf_reader and self.pdf_reader.is_dual_screen_page(self.active_page_index):
            self.preview.setHtml(
                "<p style='color: #888888; font-style: italic; line-height: 1.5;'>"
                "（このスライドの個別メモはありません。<br>"
                "上部の「📄 PDFノート画面」からBeamer組版のノート画面を表示できます。<br>"
                "「✏️ 編集」ボタンで自由なメモを追加できます）</p>"
            )
        else:
            self.preview.setHtml("<p style='color: #666666; font-style: italic;'>（このスライドのノートはありません。「✏️ 編集」ボタンで記述できます）</p>")

    def set_pdf_reader(self, reader: PdfReader):
        self.pdf_reader = reader

    def set_page(self, index: int, next_pixmap: QPixmap | None):
        # ページ切り替え前に現ページのノートを保存
        self.save_current_note_to_memory()

        self.active_page_index = index

        # 次のスライド画像表示
        if next_pixmap and not next_pixmap.isNull():
            scaled = next_pixmap.scaled(280, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.next_slide_image.setPixmap(scaled)
        else:
            self.next_slide_image.clear()
            self.next_slide_image.setText("（最後のスライドです）")
            self.next_slide_image.setStyleSheet(
                "background-color: #161618; color: #666666; font-size: 11px; border: 1px solid #333336; border-radius: 4px;"
            )

        # PDFノート画面画像（2画面レイアウト時）の取得
        has_note_image = False
        self._current_note_pixmap = None

        if self.pdf_reader:
            has_note_image = self.pdf_reader.is_dual_screen_page(index)
            if has_note_image:
                self._current_note_pixmap = self.pdf_reader.get_embedded_note_image(index)

        # ツールバーボタンの表示切り替え
        self.btn_pdf_note_view.setVisible(has_note_image)

        # PDFノート画像の更新
        self._update_pdf_note_image_display()

        # ユーザー手動ノート読み込み
        manual_note = ""
        if self.pdf_reader and index in self.pdf_reader.notes:
            manual_note = self.pdf_reader.notes[index]

        # エディタの初期テキスト
        self.editor.blockSignals(True)
        self.editor.setPlainText(manual_note)
        self.editor.blockSignals(False)

        self.lbl_page_note.setText(f"スライド {index + 1}")
        self.save_status_label.setText("")

        # ビュー状態の復元
        if self.btn_pdf_note_view.isChecked() and has_note_image:
            self.note_stack.setCurrentIndex(2)
        elif self.btn_edit.isChecked():
            self.note_stack.setCurrentIndex(0)
        else:
            self.btn_pdf_note_view.setChecked(False)
            self._render_preview(manual_note)
            self.note_stack.setCurrentIndex(1)

    def _on_note_text_changed(self):
        self.save_status_label.setText("編集中...")
        self.save_timer.start()

    def save_current_note_to_memory(self):
        if self.pdf_reader is not None:
            text = self.editor.toPlainText()
            self.pdf_reader.save_note(self.active_page_index, text)

    def _auto_save_to_file(self):
        self.save_current_note_to_memory()
        if self.pdf_reader is not None:
            try:
                self.pdf_reader.save_note_to_file()
                self.save_status_label.setText("✓ 保存済み")
            except Exception:
                self.save_status_label.setText("⚠ 保存エラー")
