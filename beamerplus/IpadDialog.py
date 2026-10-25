import os
import urllib.parse
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QApplication, QLineEdit
)
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QColor

from beamerplus.WebServer import get_local_ip, WebBridge, generate_passcode


class IpadDialog(QDialog):
    def __init__(
        self,
        bridge: WebBridge,
        http_port: int = 8080,
        passcode: str = "",
        server=None,
        on_passcode_changed=None,
        parent=None
    ):
        super().__init__(parent)
        self.bridge = bridge
        self.http_port = http_port
        self.passcode = passcode
        self.server = server
        self.on_passcode_changed = on_passcode_changed

        self.setWindowTitle("📱 iPad / タブレット連携")
        self.setFixedSize(460, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #f0f0f0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #2b2b36;
                color: #ffffff;
                border: 1px solid #3f3f50;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #383848;
                border-color: #55556c;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(12)

        # ヘッダー
        title_label = QLabel("📱 iPad から手書き書き込み・リモート操作")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        desc_label = QLabel(
            "同じ Wi-Fi に接続した iPad の Safari から以下の URL を開いてください。\n"
            "スライドを見ながら Apple Pencil で直接書き込みができます。"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #a0a0b0; font-size: 12px; line-height: 1.4;")
        layout.addWidget(desc_label)

        # URL カード表示
        url_card = QFrame()
        url_card.setStyleSheet("""
            QFrame {
                background-color: #141418;
                border: 1px solid #2e2e3e;
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(url_card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        self.local_ip = get_local_ip()
        self.base_url = f"http://{self.local_ip}:{self.http_port}"
        self.auth_url = f"{self.base_url}/?code={self.passcode}" if self.passcode else self.base_url

        self.url_label = QLabel(self.base_url)
        url_font = QFont("Monospace", 14, QFont.Weight.Bold)
        self.url_label.setFont(url_font)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.url_label.setStyleSheet("color: #38bdf8; padding: 2px;")
        card_layout.addWidget(self.url_label)

        if self.passcode:
            passcode_box = QHBoxLayout()
            passcode_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            passcode_box.setSpacing(8)

            lbl_pass_title = QLabel("🔑 パスコード:")
            lbl_pass_title.setStyleSheet("color: #a0a0b0; font-size: 13px; font-weight: 500;")

            # 直接編集可能なパスコード入力欄
            self.passcode_input = QLineEdit(self.passcode)
            self.passcode_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.passcode_input.setMaxLength(32)
            self.passcode_input.setStyleSheet("""
                QLineEdit {
                    color: #fbbf24;
                    font-size: 15px;
                    font-weight: bold;
                    letter-spacing: 2px;
                    background-color: #242430;
                    padding: 3px 8px;
                    border: 1px solid #3f3f50;
                    border-radius: 6px;
                    min-width: 130px;
                    max-width: 150px;
                }
                QLineEdit:focus {
                    border-color: #38bdf8;
                    background-color: #1a1a24;
                }
            """)
            self.passcode_input.textEdited.connect(self._on_passcode_edited)

            # 更新マークの矢印のみの変更ボタン（クリックでランダム再生成）
            self.btn_refresh = QPushButton("🔄")
            self.btn_refresh.setToolTip("ランダムな英数字8桁パスコードを再生成")
            self.btn_refresh.setFixedSize(30, 30)
            self.btn_refresh.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b36;
                    color: #ffffff;
                    border: 1px solid #3f3f50;
                    border-radius: 6px;
                    font-size: 14px;
                    padding: 0;
                }
                QPushButton:hover {
                    background-color: #383848;
                    border-color: #38bdf8;
                }
                QPushButton:pressed {
                    background-color: #007acc;
                }
            """)
            self.btn_refresh.clicked.connect(self._regenerate_passcode)

            passcode_box.addWidget(lbl_pass_title)
            passcode_box.addWidget(self.passcode_input)
            passcode_box.addWidget(self.btn_refresh)

            card_layout.addLayout(passcode_box)

        # ボタン行
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_copy = QPushButton("📋 URLをコピー")
        self.btn_copy.setToolTip("パスコード付きURLをコピー")
        self.btn_copy.clicked.connect(self._copy_url)
        btn_layout.addWidget(self.btn_copy)

        card_layout.addLayout(btn_layout)
        layout.addWidget(url_card)

        # QRコード表示領域（中央揃え）
        qr_center_box = QHBoxLayout()
        qr_center_box.addStretch()

        qr_card = QFrame()
        qr_card.setFixedSize(200, 200)
        qr_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px solid #38bdf8;
                border-radius: 12px;
            }
        """)
        qr_card_layout = QVBoxLayout(qr_card)
        qr_card_layout.setContentsMargins(10, 10, 10, 10)
        qr_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_label = QLabel()
        self.qr_label.setFixedSize(180, 180)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background-color: transparent;")
        qr_card_layout.addWidget(self.qr_label)

        qr_center_box.addWidget(qr_card)
        qr_center_box.addStretch()
        layout.addLayout(qr_center_box)

        self._load_qr_code()

        # 接続状態インジケータ
        status_box = QHBoxLayout()
        status_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_box.setSpacing(6)
        self.status_icon = QLabel("●")
        self.status_icon.setStyleSheet("color: #f43f5e; font-size: 12px;")
        self.status_text = QLabel("接続待機中...")
        self.status_text.setStyleSheet("color: #a0a0b0; font-size: 13px; font-weight: 500;")
        status_box.addWidget(self.status_icon)
        status_box.addWidget(self.status_text)
        layout.addLayout(status_box)

        layout.addStretch(1)

        # 閉じるボタン
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        # シグナル接続
        self.bridge.client_count_changed.connect(self.update_client_count)

    def _on_passcode_edited(self, text: str):
        self._apply_passcode(text.strip(), update_input=False)

    def _regenerate_passcode(self):
        new_code = generate_passcode(8)
        if hasattr(self, "passcode_input"):
            self.passcode_input.setText(new_code)
        self._apply_passcode(new_code, update_input=False)

    def _apply_passcode(self, new_passcode: str, update_input: bool = True):
        self.passcode = new_passcode
        if update_input and hasattr(self, "passcode_input"):
            self.passcode_input.setText(self.passcode)
        self.auth_url = f"{self.base_url}/?code={self.passcode}" if self.passcode else self.base_url
        self._load_qr_code()
        self.btn_copy.setText("📋 URLをコピー")
        self.btn_copy.setStyleSheet("")

        if self.server and hasattr(self.server, "set_passcode"):
            self.server.set_passcode(self.passcode)
        if self.on_passcode_changed:
            self.on_passcode_changed(self.passcode)

    def set_passcode(self, new_passcode: str):
        self._apply_passcode(str(new_passcode).strip(), update_input=True)

    def _copy_url(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.auth_url)
        self.btn_copy.setText("✓ コピー完了")
        self.btn_copy.setStyleSheet("background-color: #10b981; color: white;")

    def _load_qr_code(self):
        """公式 qrcode (PIL) ライブラリを使用して高精細かつ正確な QR コードを生成・描画"""
        try:
            import io
            import qrcode

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,  # ISO規格に準拠したクワイエットゾーン（最低4マス）
            )
            qr.add_data(self.auth_url)
            qr.make(fit=True)

            pil_img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")

            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())

            self.qr_label.setPixmap(
                pixmap.scaled(
                    180, 180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            return
        except Exception as e:
            print(f"[BeamerPlus] QR Code generation error: {e}")

        # 万が一のエラー時のフォールバック案内
        pixmap = QPixmap(180, 180)
        pixmap.fill(QColor("#ffffff"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#333333"))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(
            pixmap.rect().adjusted(6, 6, -6, -6),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            f"iPad Safari で\n開いてください:\n\n{self.base_url}"
        )
        painter.end()
        self.qr_label.setPixmap(pixmap)

    def update_client_count(self, count: int):
        if count > 0:
            self.status_icon.setStyleSheet("color: #10b981; font-size: 12px;")
            self.status_text.setText(f"iPad 接続中: {count} 台")
            self.status_text.setStyleSheet("color: #10b981; font-size: 13px; font-weight: bold;")
        else:
            self.status_icon.setStyleSheet("color: #f43f5e; font-size: 12px;")
            self.status_text.setText("接続待機中...")
            self.status_text.setStyleSheet("color: #a0a0b0; font-size: 13px; font-weight: 500;")
