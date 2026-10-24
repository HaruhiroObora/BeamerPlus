import os
from PySide6.QtCore import Qt, QTimer, QTime, QEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QToolBar, QPushButton, QLabel, QFrame,
    QApplication
)
from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from beamerplus.PdfReader import PdfReader
from beamerplus.DrawingModel import PresentationController
from beamerplus.ThumbnailBar import ThumbnailBar
from beamerplus.SimpleView import SimpleView
from beamerplus.NotePanel import NotePanel
from beamerplus.Viewer import Viewer


class MainWindow(QMainWindow):
    def __init__(self, viewer: Viewer | None = None):
        super().__init__()

        self.setWindowTitle("BeamerPlus 発表者ビュー")
        self.resize(1200, 800)

        self.controller = PresentationController(self)
        self.viewer = viewer
        if self.viewer:
            self.viewer.connect_controller(self.controller)
            self.viewer.blank_state_changed.connect(self._on_blank_state_changed)

        self.pdf_reader: PdfReader | None = None
        self.render_dpi: int = 400  # デフォルト: 4K 超高精細 (400 DPI)

        # プレゼンタイマー
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_timer)
        self.presentation_time = QTime(0, 0, 0)

        # メインレイアウト
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 中央スプリッター (左: スライド画面＋ツールバー, 右: ノートパネル)
        self.center_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.center_splitter.setStyleSheet(
            "QSplitter::handle { background-color: #333336; width: 4px; }"
        )

        # 1. メインスライド操作領域（ポインタ・ペンなどのツールバー ＋ キャンバス：常時表示）
        self.slide_view = SimpleView(self.controller)
        self.center_splitter.addWidget(self.slide_view)

        # 2. ノートパネル（右サイド、表示/非表示切り替え可能）
        self.note_panel = NotePanel()
        self.center_splitter.addWidget(self.note_panel)

        # スプリッターの比率設定 (スライド: 70%, ノート: 30%)
        self.center_splitter.setStretchFactor(0, 7)
        self.center_splitter.setStretchFactor(1, 3)

        self.main_layout.addWidget(self.center_splitter, 1)

        # 3. 下部: スライド一覧（ThumbnailBar、表示/非表示切り替え可能）
        self.thumbnail_bar = ThumbnailBar()
        self.thumbnail_bar.page_selected.connect(self.controller.set_page)
        self.main_layout.addWidget(self.thumbnail_bar)

        # コントローラからのシグナル受信
        self.controller.page_changed.connect(self._on_page_changed)

        # UIメニューとツールバー作成
        self._create_menus_and_toolbars()

        # スタイル設定
        self.setStyleSheet(
            "QMainWindow { background-color: #1e1e1e; color: #ffffff; }"
            "QToolBar { background-color: #2d2d30; border-bottom: 1px solid #3e3e42; spacing: 6px; padding: 3px; }"
            "QMenuBar { background-color: #2d2d30; color: #cccccc; }"
            "QMenuBar::item:selected { background-color: #3e3e42; }"
            "QMenu { background-color: #252526; color: #cccccc; border: 1px solid #3e3e42; }"
            "QMenu::item:selected { background-color: #094771; }"
        )

    def _create_menus_and_toolbars(self):
        menu_bar = self.menuBar()

        # ファイルメニュー
        file_menu = menu_bar.addMenu("ファイル(&F)")
        
        open_action = QAction("開く(&O)...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)
        file_menu.addAction(open_action)

        save_notes_action = QAction("ノートを保存(&S)", self)
        save_notes_action.setShortcut(QKeySequence.StandardKey.Save)
        save_notes_action.triggered.connect(self.save_notes)
        file_menu.addAction(save_notes_action)

        file_menu.addSeparator()

        quit_action = QAction("終了(&Q)", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 表示メニュー
        view_menu = menu_bar.addMenu("表示(&V)")

        self.act_toggle_notes = QAction("ノートパネルの表示/非表示", self)
        self.act_toggle_notes.setShortcut("Ctrl+N")
        self.act_toggle_notes.setCheckable(True)
        self.act_toggle_notes.setChecked(True)
        self.act_toggle_notes.triggered.connect(self.toggle_note_panel)
        view_menu.addAction(self.act_toggle_notes)

        self.act_toggle_thumbnails = QAction("スライド一覧バーの表示/非表示", self)
        self.act_toggle_thumbnails.setShortcut("Ctrl+T")
        self.act_toggle_thumbnails.setCheckable(True)
        self.act_toggle_thumbnails.setChecked(True)
        self.act_toggle_thumbnails.triggered.connect(self.toggle_thumbnail_bar)
        view_menu.addAction(self.act_toggle_thumbnails)

        self.act_toggle_toolbar = QAction("メインツールバーの表示/非表示", self)
        self.act_toggle_toolbar.setCheckable(True)
        self.act_toggle_toolbar.setChecked(True)
        self.act_toggle_toolbar.triggered.connect(self.toggle_main_toolbar)
        view_menu.addAction(self.act_toggle_toolbar)

        view_menu.addSeparator()

        # 画質設定サブメニュー
        quality_menu = view_menu.addMenu("レンダリング画質(&Q)")
        self.dpi_group = QActionGroup(self)
        self.dpi_group.setExclusive(True)

        for label, dpi in [
            ("高画質 (250 DPI - フルHD向け)", 250),
            ("4K 超高精細 (400 DPI - デフォルト/4K向け)", 400),
            ("5K / Ultra (500 DPI)", 500),
        ]:
            action = QAction(label, self, checkable=True)
            if dpi == self.render_dpi:
                action.setChecked(True)
            action.triggered.connect(lambda checked, d=dpi: self.set_render_dpi(d))
            self.dpi_group.addAction(action)
            quality_menu.addAction(action)

        # プレゼンテーションメニュー
        pres_menu = menu_bar.addMenu("プレゼンテーション(&P)")

        act_proj_toggle = QAction("プロジェクタ画面の表示/非表示", self)
        act_proj_toggle.setShortcut("F5")
        act_proj_toggle.triggered.connect(self.toggle_viewer_window)
        pres_menu.addAction(act_proj_toggle)

        act_proj_fullscreen = QAction("プロジェクタ画面を全画面表示", self)
        act_proj_fullscreen.setShortcut("F11")
        act_proj_fullscreen.triggered.connect(self.fullscreen_viewer)
        pres_menu.addAction(act_proj_fullscreen)

        act_blank = QAction("画面を暗転 (ブラックアウト)", self)
        act_blank.setShortcut("B")
        act_blank.triggered.connect(self.toggle_blank_screen)
        pres_menu.addAction(act_blank)

        # 上部ツールバー
        self.main_toolbar = QToolBar("メインツールバー")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(self.main_toolbar)

        btn_open = QPushButton("📁 開く")
        btn_open.setStyleSheet(self._tb_btn_style())
        btn_open.clicked.connect(self.open_file_dialog)
        self.main_toolbar.addWidget(btn_open)

        self.main_toolbar.addSeparator()

        # 表示トグルボタン: ノート
        self.btn_toggle_notes = QPushButton("📝 ノート")
        self.btn_toggle_notes.setCheckable(True)
        self.btn_toggle_notes.setChecked(True)
        self.btn_toggle_notes.setStyleSheet(self._tb_btn_style())
        self.btn_toggle_notes.setToolTip("ノートパネルの表示/非表示 (Ctrl+N)")
        self.btn_toggle_notes.clicked.connect(self.toggle_note_panel)
        self.main_toolbar.addWidget(self.btn_toggle_notes)

        # 表示トグルボタン: スライド一覧
        self.btn_toggle_thumbs = QPushButton("🎞️ スライド一覧")
        self.btn_toggle_thumbs.setCheckable(True)
        self.btn_toggle_thumbs.setChecked(True)
        self.btn_toggle_thumbs.setStyleSheet(self._tb_btn_style())
        self.btn_toggle_thumbs.setToolTip("スライド一覧バーの表示/非表示 (Ctrl+T)")
        self.btn_toggle_thumbs.clicked.connect(self.toggle_thumbnail_bar)
        self.main_toolbar.addWidget(self.btn_toggle_thumbs)

        self.main_toolbar.addSeparator()

        # タイマー表示
        self.lbl_timer = QLabel("⏱️ 00:00:00")
        self.lbl_timer.setStyleSheet("color: #4fc3f7; font-size: 13px; margin-left: 8px;")
        self.lbl_timer.setFixedWidth(105)
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_toolbar.addWidget(self.lbl_timer)

        self.btn_timer_toggle = QPushButton("▶ 開始")
        self.btn_timer_toggle.setStyleSheet(self._tb_btn_style())
        self.btn_timer_toggle.setFixedWidth(100)
        self.btn_timer_toggle.clicked.connect(lambda: self._toggle_timer(self.btn_timer_toggle))
        self.main_toolbar.addWidget(self.btn_timer_toggle)

        btn_timer_reset = QPushButton("↺ リセット")
        btn_timer_reset.setStyleSheet(self._tb_btn_style())
        btn_timer_reset.clicked.connect(self._reset_timer)
        self.main_toolbar.addWidget(btn_timer_reset)

        self.main_toolbar.addSeparator()

        # プロジェクタ画面制御ボタン
        btn_viewer = QPushButton("📽️ プロジェクタ画面")
        btn_viewer.setStyleSheet(self._tb_btn_style())
        btn_viewer.clicked.connect(self.toggle_viewer_window)
        self.main_toolbar.addWidget(btn_viewer)

        self.btn_blank = QPushButton("⬛ 暗転 (B)")
        self.btn_blank.setStyleSheet(self._tb_btn_style())
        self.btn_blank.setFixedWidth(120)
        self.btn_blank.setToolTip("プロジェクタ画面を一時的に真っ黒にします (B)")
        self.btn_blank.clicked.connect(self.toggle_blank_screen)
        self.main_toolbar.addWidget(self.btn_blank)

        # ツールバーの全ボタンからフォーカスを外す（クリック後に矢印キーが吸われないようにする）
        for btn in (
            btn_open, self.btn_toggle_notes, self.btn_toggle_thumbs,
            self.btn_timer_toggle, btn_timer_reset, btn_viewer, self.btn_blank
        ):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # アプリケーション全体のキーイベントフィルターを登録
        # （ボタンやスライダー等の操作後でも、ノート編集中でなければ矢印キー等で確実にスライド操作可能にする）
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _tb_btn_style(self) -> str:
        return (
            "QPushButton { background-color: #3e3e42; color: #ffffff; border: 1px solid #555555; border-radius: 3px; padding: 4px 10px; font-size: 12px; }"
            "QPushButton:hover { background-color: #505054; }"
            "QPushButton:checked { background-color: #007acc; border-color: #0098ff; }"
        )

    def set_render_dpi(self, dpi: int):
        if self.render_dpi != dpi:
            self.render_dpi = dpi
            if self.pdf_reader:
                self._update_current_page_display(self.controller.current_page)

    def toggle_note_panel(self):
        """ノートパネルの表示/非表示切り替え (Ctrl+N)"""
        is_visible = not self.note_panel.isVisible()
        self.note_panel.setVisible(is_visible)
        self.btn_toggle_notes.setChecked(is_visible)
        self.act_toggle_notes.setChecked(is_visible)

    def toggle_thumbnail_bar(self):
        """スライド一覧バーの表示/非表示切り替え (Ctrl+T)"""
        is_visible = not self.thumbnail_bar.isVisible()
        self.thumbnail_bar.setVisible(is_visible)
        self.btn_toggle_thumbs.setChecked(is_visible)
        self.act_toggle_thumbnails.setChecked(is_visible)

    def toggle_main_toolbar(self):
        """メインツールバーの表示/非表示切り替え"""
        is_visible = not self.main_toolbar.isVisible()
        self.main_toolbar.setVisible(is_visible)
        self.act_toggle_toolbar.setChecked(is_visible)

    def createPopupMenu(self):
        """ツールバー右クリック時のデフォルトコンテキストメニューを無効化"""
        return None

    def toggle_viewer_window(self):
        if not self.viewer:
            return
        if self.viewer.isVisible():
            self.viewer.hide()
        else:
            self.viewer.show()
            self.viewer.fit_view()

    def fullscreen_viewer(self):
        if self.viewer:
            self.viewer.show()
            self.viewer.toggle_fullscreen()

    def toggle_blank_screen(self):
        if self.viewer:
            self.viewer.toggle_blank()

    def _on_blank_state_changed(self, is_blank: bool):
        if hasattr(self, "btn_blank"):
            if is_blank:
                self.btn_blank.setText("⬛ 暗転中 (B)")
                self.btn_blank.setStyleSheet(
                    "QPushButton { background-color: #b71c1c; color: #ffffff; border: 1px solid #f44336; border-radius: 3px; padding: 4px 10px; font-size: 12px; }"
                )
            else:
                self.btn_blank.setText("⬛ 暗転 (B)")
                self.btn_blank.setStyleSheet(self._tb_btn_style())

    def _toggle_timer(self, button: QPushButton):
        if self.elapsed_timer.isActive():
            self.elapsed_timer.stop()
            button.setText("▶ 再開")
        else:
            self.elapsed_timer.start()
            button.setText("⏸ 一時停止")

    def _reset_timer(self):
        self.presentation_time = QTime(0, 0, 0)
        self.lbl_timer.setText("⏱️ 00:00:00")

    def _update_timer(self):
        self.presentation_time = self.presentation_time.addSecs(1)
        self.lbl_timer.setText(f"⏱️ {self.presentation_time.toString('hh:mm:ss')}")

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "PDFスライドを開く",
            "",
            "PDFファイル (*.pdf)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if path:
            self.load_pdf(path)

    def load_pdf(self, path: str):
        try:
            self.pdf_reader = PdfReader(path)
            self.controller.set_total_pages(len(self.pdf_reader))
            self.note_panel.set_pdf_reader(self.pdf_reader)
            self.thumbnail_bar.load_pdf(self.pdf_reader)
            self.setWindowTitle(f"BeamerPlus 発表者ビュー - {os.path.basename(path)}")

            # 最初のページを表示
            self.controller.set_page(0)
            self._update_current_page_display(0)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"PDFファイルの読み込みに失敗しました:\n{str(e)}")

    def _on_page_changed(self, index: int):
        self._update_current_page_display(index)

    def _update_current_page_display(self, index: int):
        if not self.pdf_reader:
            return

        # スライド画像取得 (高解像度 DPI)
        current_pixmap = self.pdf_reader.get_page_image(index, auto_crop=True, dpi=self.render_dpi)
        total = len(self.pdf_reader)

        next_pixmap = None
        if index + 1 < total:
            next_pixmap = self.pdf_reader.get_page_image(index + 1, auto_crop=True, dpi=self.render_dpi)

        # プロジェクタ（Viewer）更新
        if self.viewer and current_pixmap:
            self.viewer.show_image(current_pixmap)

        # メインスライド表示領域（ツールバー＋キャンバス）更新
        self.slide_view.set_pixmap(current_pixmap)
        self.slide_view.update_page_info(index, total)

        # ノートパネル更新
        self.note_panel.set_page(index, next_pixmap)

        # サムネイルバー更新
        self.thumbnail_bar.set_current_page(index)

    def save_notes(self):
        if self.pdf_reader:
            self.note_panel.save_current_note_to_memory()
            try:
                self.pdf_reader.save_note_to_file()
                QMessageBox.information(self, "保存完了", "ノートをファイルに保存しました。")
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"ノートの保存に失敗しました:\n{str(e)}")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            # ノートエディタ編集中やスライド上のテキスト入力中は通常の文字入力・カーソル移動を最優先
            if hasattr(self, "note_panel") and self.note_panel.editor.hasFocus():
                return super().eventFilter(watched, event)
            if hasattr(self, "slide_view") and hasattr(self.slide_view, "canvas") and hasattr(self.slide_view.canvas, "text_input") and self.slide_view.canvas.text_input.hasFocus():
                return super().eventFilter(watched, event)

            key = event.key()
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
                self.controller.next_page()
                return True
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
                self.controller.prev_page()
                return True
            elif key == Qt.Key.Key_B:
                if self.viewer:
                    self.viewer.toggle_blank()
                return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        key = event.key()
        # エディタ編集中やテキスト入力中でない場合のみページ送りショートカットを有効化
        is_typing = (
            (hasattr(self, "note_panel") and self.note_panel.editor.hasFocus()) or
            (hasattr(self, "slide_view") and hasattr(self.slide_view, "canvas") and hasattr(self.slide_view.canvas, "text_input") and self.slide_view.canvas.text_input.hasFocus())
        )
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            if not is_typing:
                self.controller.next_page()
                return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            if not is_typing:
                self.controller.prev_page()
                return
        elif key == Qt.Key.Key_B:
            if not is_typing and self.viewer:
                self.viewer.toggle_blank()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.pdf_reader:
            self.note_panel.save_current_note_to_memory()
            try:
                self.pdf_reader.save_note_to_file()
            except Exception:
                pass
        if self.viewer:
            self.viewer.close()
        super().closeEvent(event)
