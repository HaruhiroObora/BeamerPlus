from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QColorDialog, QToolButton, QLabel, QFrame, QSlider
)
from PySide6.QtGui import QColor, QPixmap

from beamerplus.DrawingModel import PresentationController
from beamerplus.SlideCanvas import SlideCanvas


class SimpleView(QWidget):
    def __init__(self, controller: PresentationController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ツールバー作成
        self.toolbar = self._create_toolbar()
        layout.addWidget(self.toolbar)

        # スライドキャンバス
        self.canvas = SlideCanvas(self.controller)
        layout.addWidget(self.canvas, 1)

        # コントローラシグナル接続
        self.controller.tool_changed.connect(self._on_tool_changed)
        self.controller.tool_size_changed.connect(self._on_tool_size_changed)
        self.controller.line_mode_changed.connect(self._on_line_mode_changed)
        self.controller.color_changed.connect(self._on_color_changed)

        # 初期表示の更新
        self._on_tool_changed(self.controller.current_tool)

    def _create_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet(
            "QFrame { background-color: #252526; border-bottom: 1px solid #333333; }"
            "QPushButton, QToolButton { background-color: #333333; color: #ffffff; border: 1px solid #444444; border-radius: 4px; padding: 4px 10px; font-size: 12px; }"
            "QPushButton:hover, QToolButton:hover { background-color: #444444; }"
            "QPushButton:checked, QToolButton:checked { background-color: #007acc; border-color: #0098ff; font-weight: bold; }"
            "QLabel { color: #cccccc; font-size: 12px; }"
            "QSlider::groove:horizontal { height: 4px; background: #444448; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #007acc; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #ffffff; width: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }"
            "QSlider::handle:horizontal:hover { background: #4fc3f7; }"
        )
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 4, 10, 4)
        bar_layout.setSpacing(6)

        # 基本ツールボタン
        self.btn_pointer = QPushButton("🔴 ポインタ")
        self.btn_pointer.setCheckable(True)
        self.btn_pointer.setToolTip("レーザーポインタ (もう一度クリックで通常モード)")
        self.btn_pointer.clicked.connect(lambda: self._on_tool_btn_clicked("pointer"))
        bar_layout.addWidget(self.btn_pointer)

        self.btn_pen = QPushButton("✏️ ペン")
        self.btn_pen.setCheckable(True)
        self.btn_pen.setToolTip("手書きペン (もう一度クリックで通常モード)")
        self.btn_pen.clicked.connect(lambda: self._on_tool_btn_clicked("pen"))
        bar_layout.addWidget(self.btn_pen)

        self.btn_highlighter = QPushButton("🖍️ 蛍光ペン")
        self.btn_highlighter.setCheckable(True)
        self.btn_highlighter.setToolTip("蛍光ペン (もう一度クリックで通常モード)")
        self.btn_highlighter.clicked.connect(lambda: self._on_tool_btn_clicked("highlighter"))
        bar_layout.addWidget(self.btn_highlighter)

        self.btn_eraser = QPushButton("🧹 消しゴム")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.setToolTip("ストローク消しゴム (なぞった線を消去、もう一度クリックで通常モード)")
        self.btn_eraser.clicked.connect(lambda: self._on_tool_btn_clicked("eraser"))
        bar_layout.addWidget(self.btn_eraser)

        self.tool_buttons = {
            "pointer": self.btn_pointer,
            "pen": self.btn_pen,
            "highlighter": self.btn_highlighter,
            "eraser": self.btn_eraser,
        }

        # 直線修飾ボタン（ペンまたは蛍光ペンで直線を引く）
        self.btn_line = QPushButton("📏 直線")
        self.btn_line.setCheckable(True)
        self.btn_line.setToolTip("選択中のペン/蛍光ペンで直線を引く（もう一度クリックでフリーハンドに戻る）")
        self.btn_line.clicked.connect(self._on_line_btn_clicked)
        bar_layout.addWidget(self.btn_line)

        # ペン / 蛍光ペンの色選択ボタン
        self.btn_color = QPushButton("■")
        self.btn_color.setToolTip("選択中ツール（ペン/蛍光ペン）の色を変更")
        self.btn_color.setStyleSheet(f"color: {self.controller.pen_color}; font-size: 16px; padding: 2px 8px;")
        self.btn_color.clicked.connect(self._choose_color)
        bar_layout.addWidget(self.btn_color)

        # 区切り線
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #444444;")
        bar_layout.addWidget(sep1)

        # --- 共通サイズスライダー ---
        self.lbl_size_title = QLabel("太さ:")
        self.lbl_size_title.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        bar_layout.addWidget(self.lbl_size_title)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, 40)
        self.size_slider.setValue(18)
        self.size_slider.setFixedWidth(80)
        self.size_slider.setToolTip("選択中ツールの太さ・半径を変更")
        self.size_slider.valueChanged.connect(self._on_slider_value_changed)
        bar_layout.addWidget(self.size_slider)

        self.lbl_size_val = QLabel("18")
        self.lbl_size_val.setFixedWidth(20)
        self.lbl_size_val.setStyleSheet("color: #4fc3f7; font-size: 11px; font-weight: bold;")
        bar_layout.addWidget(self.lbl_size_val)

        # 区切り線
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #444444;")
        bar_layout.addWidget(sep2)

        # Undo & Clear
        self.btn_undo = QPushButton("↩ 元に戻す")
        self.btn_undo.clicked.connect(self.controller.undo_current_page_stroke)
        bar_layout.addWidget(self.btn_undo)

        self.btn_clear = QPushButton("🗑 描画消去")
        self.btn_clear.clicked.connect(self.controller.clear_current_page_strokes)
        bar_layout.addWidget(self.btn_clear)

        bar_layout.addStretch()

        # ページ送りボタン
        self.btn_prev = QPushButton("◀ 前へ")
        self.btn_prev.clicked.connect(self.controller.prev_page)
        bar_layout.addWidget(self.btn_prev)

        self.page_label = QLabel("0 / 0")
        bar_layout.addWidget(self.page_label)

        self.btn_next = QPushButton("次へ ▶")
        self.btn_next.clicked.connect(self.controller.next_page)
        bar_layout.addWidget(self.btn_next)

        return bar

    def _on_tool_btn_clicked(self, tool_name: str):
        if self.controller.current_tool == tool_name:
            # 有効になっている機能のボタンをクリックしたら通常モード（hand）に戻る
            self.controller.set_line_mode(False)
            self.controller.set_tool("hand")
        else:
            self.controller.set_tool(tool_name)

    def _on_line_btn_clicked(self):
        self.controller.toggle_line_mode()

    def _on_line_mode_changed(self, is_line: bool):
        self.btn_line.setChecked(is_line)

    def _choose_color(self):
        # 現在アクティブなツール（蛍光ペンなら蛍光ペン、それ以外ならペン）の色を変更
        target_tool = "highlighter" if self.controller.current_tool == "highlighter" else "pen"
        current_color = self.controller.get_tool_color(target_tool)
        title = "蛍光ペンの色選択" if target_tool == "highlighter" else "ペンの色選択"

        color = QColorDialog.getColor(QColor(current_color), self, title)
        if color.isValid():
            hex_color = color.name()
            self.controller.set_tool_color(target_tool, hex_color)
            self._update_color_button()

    def _update_color_button(self):
        tool = self.controller.current_tool
        if tool == "highlighter":
            col = self.controller.highlighter_color
            self.btn_color.setEnabled(True)
            self.btn_color.setToolTip("蛍光ペンの色を変更")
        elif tool == "eraser":
            col = "#555555"
            self.btn_color.setEnabled(False)
            self.btn_color.setToolTip("消しゴム選択中は色変更不可")
        else:
            # pen, pointer, hand
            col = self.controller.pen_color
            self.btn_color.setEnabled(True)
            self.btn_color.setToolTip("ペンの色を変更")

        self.btn_color.setStyleSheet(f"color: {col}; font-size: 16px; padding: 2px 8px;")

    def _on_color_changed(self, tool_name: str, hex_color: str):
        self._update_color_button()

    def _on_slider_value_changed(self, val: int):
        self.controller.set_current_tool_size(val)
        self.lbl_size_val.setText(str(val))

    def _on_tool_changed(self, tool_name: str):
        # 1. 各ボタンのチェック状態を同期
        for name, btn in self.tool_buttons.items():
            btn.setChecked(name == tool_name)
        self.btn_line.setChecked(self.controller.is_line_mode)

        # 2. 色選択ボタンの更新
        self._update_color_button()

        # 3. 直線ボタンの有効化/無効化（消しゴム時は無効）
        self.btn_line.setEnabled(tool_name != "eraser")

        # 4. スライダーを該当ツールの保持サイズに更新
        if tool_name == "hand":
            self.size_slider.setEnabled(False)
            self.lbl_size_title.setText("サイズ:")
            self.lbl_size_val.setText("-")
        else:
            self.size_slider.setEnabled(True)
            if tool_name in ("pointer", "eraser"):
                self.lbl_size_title.setText("半径:")
            else:
                self.lbl_size_title.setText("太さ:")

            size = self.controller.get_tool_size(tool_name)
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(size)
            self.size_slider.blockSignals(False)
            self.lbl_size_val.setText(str(size))

    def _on_tool_size_changed(self, tool_name: str, size: int):
        if tool_name == self.controller.current_tool:
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(size)
            self.size_slider.blockSignals(False)
            self.lbl_size_val.setText(str(size))

    def set_pixmap(self, pixmap: QPixmap | None):
        self.canvas.set_pixmap(pixmap)

    def update_page_info(self, current: int, total: int):
        self.page_label.setText(f"{current + 1} / {total}")
        self.btn_prev.setEnabled(current > 0)
        self.btn_next.setEnabled(current < total - 1)
