from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit,
    QPlainTextEdit, QLabel, QPushButton, QStackedWidget, QFrame
)
from PySide6.QtGui import QPixmap, QFont

from beamerplus.PdfReader import PdfReader


class NotePanel(QWidget):
    """
    発表者画面のサイドに配置されるノートパネル
    （次のスライドプレビュー ＋ Markdown形式ノートの閲覧・編集）
    デフォルトはプレビューモードで表示され、「✏️ 編集」ボタンで直接編集可能。
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.pdf_reader: PdfReader | None = None
        self.active_page_index: int = 0

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
        self.lbl_title.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: bold;")
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
        next_header.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
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

        # エディタ操作ツールバー（「プレビュー」ボタンは廃止し、「✏️ 編集」トグルボタンのみ）
        tb_layout = QHBoxLayout()
        self.lbl_page_note = QLabel("スライド 1")
        self.lbl_page_note.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        tb_layout.addWidget(self.lbl_page_note)
        tb_layout.addStretch()

        self.btn_edit = QPushButton("✏️ 編集")
        self.btn_edit.setCheckable(True)
        self.btn_edit.setChecked(False)  # デフォルトはプレビューモード（未選択）
        self.btn_edit.setToolTip("ノートを編集する（もう一度クリックでプレビューに戻る）")
        self.btn_edit.setStyleSheet(self._btn_style())
        self.btn_edit.clicked.connect(self._toggle_edit_mode)
        tb_layout.addWidget(self.btn_edit)

        note_layout.addLayout(tb_layout)

        # スタックウィジェット (index 0: 編集 QPlainTextEdit, index 1: プレビュー QTextEdit)
        self.note_stack = QStackedWidget()

        # エディタ
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

        # プレビュー（デフォルト表示）
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            "QTextEdit { background-color: #18181a; color: #e0e0e0; border: 1px solid #38383c; border-radius: 4px; padding: 8px; }"
        )
        self.note_stack.addWidget(self.preview)

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
            "QPushButton:checked { background-color: #007acc; border-color: #0098ff; font-weight: bold; }"
        )

    def _toggle_edit_mode(self):
        """有効になっている機能のボタンをクリックしたらプレビューモード（デフォルト）に戻る"""
        if self.btn_edit.isChecked():
            # 編集モードへ
            self.note_stack.setCurrentIndex(0)
            self.editor.setFocus()
        else:
            # プレビューモード（デフォルト）へ戻る
            self.save_current_note_to_memory()
            md_text = self.editor.toPlainText()
            self._render_preview(md_text)
            self.note_stack.setCurrentIndex(1)

    def _render_preview(self, md_text: str):
        if not md_text.strip():
            self.preview.setHtml("<p style='color: #666666; font-style: italic;'>（このスライドのノートはありません。「✏️ 編集」ボタンで記述できます）</p>")
        else:
            self.preview.setMarkdown(md_text)

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

        # ノートテキスト読み込み
        note_text = ""
        if self.pdf_reader:
            note_text = self.pdf_reader.get_note(index) or ""

        self.editor.blockSignals(True)
        self.editor.setPlainText(note_text)
        self.editor.blockSignals(False)

        self.lbl_page_note.setText(f"スライド {index + 1}")
        self.save_status_label.setText("")

        # プレビューをレンダリング
        self._render_preview(note_text)

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
