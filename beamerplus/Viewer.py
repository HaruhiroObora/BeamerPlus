from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsPathItem, QGraphicsEllipseItem, QGraphicsSimpleTextItem
)
from PySide6.QtGui import (
    QPixmap, QPainter, QResizeEvent, QKeyEvent, QColor, QPen,
    QPainterPath, QRadialGradient, QBrush, QFont
)

from beamerplus.DrawingModel import PresentationController, Stroke, TextItem

# スライド短辺に対するポインタ半径の比率 (視認性の高い大きめのレーザーポインタ)
POINTER_RADIUS_RATIO = 0.018


class Viewer(QMainWindow):
    blank_state_changed = Signal(bool)

    def __init__(self, controller: PresentationController | None = None):
        super().__init__()

        self.setWindowTitle("BeamerPlus プロジェクタ")
        self.controller = controller

        self.graphics_view = QGraphicsView()
        self.setCentralWidget(self.graphics_view)
        self.graphics_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.graphics_view.setStyleSheet("background-color: black; border: none;")
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.scene = QGraphicsScene(self)
        self.graphics_view.setScene(self.scene)

        self.page_pixmap: QPixmap | None = None

        # スライド画像アイテム（一度作成して setPixmap で更新）
        self.pixmap_item: QGraphicsPixmapItem = self.scene.addPixmap(QPixmap())
        self.pixmap_item.setZValue(0)

        # ストローク管理
        self.stroke_items: list[QGraphicsPathItem] = []
        self.active_path_item: QGraphicsPathItem | None = None
        self.active_path: QPainterPath | None = None

        # テキスト管理
        self.text_items: list[QGraphicsSimpleTextItem] = []

        # レーザーポインタアイテム（一度作成して再利用）
        self.pointer_radius: float = 24.0
        self.pointer_item: QGraphicsEllipseItem = QGraphicsEllipseItem(
            -self.pointer_radius, -self.pointer_radius, self.pointer_radius * 2, self.pointer_radius * 2
        )
        self.pointer_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.pointer_item.setZValue(1000)  # 最前面
        self.pointer_item.setVisible(False)
        self.scene.addItem(self.pointer_item)

        # ブランクスクリーン用オーバーレイ（ウィンドウ全体を完全に黒く覆う）
        self.is_blank: bool = False
        self.blank_overlay = QWidget(self)
        self.blank_overlay.setStyleSheet("background-color: black;")
        self.blank_overlay.hide()

        if self.controller:
            self.connect_controller(self.controller)

    def connect_controller(self, controller: PresentationController):
        self.controller = controller
        controller.pointer_updated.connect(self.on_pointer_updated)
        controller.stroke_started.connect(self.on_stroke_started)
        controller.stroke_added_point.connect(self.on_stroke_added_point)
        controller.stroke_line_updated.connect(self.on_stroke_line_updated)
        controller.stroke_finished.connect(self.on_stroke_finished)
        controller.strokes_cleared.connect(self.on_strokes_cleared)
        controller.stroke_undone.connect(self.on_stroke_undone)
        controller.strokes_updated.connect(self.on_strokes_updated)
        controller.text_added.connect(self.on_text_added)
        controller.texts_updated.connect(self.on_texts_updated)
        controller.tool_size_changed.connect(self.on_tool_size_changed)

    def _setup_pointer_item(self):
        """スライド解像度とコントローラ設定に応じたポインタアイテムのサイズとグラデーションを更新"""
        if not self.page_pixmap or self.page_pixmap.isNull():
            return

        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        base_dim = min(w, h)
        pointer_size = self.controller.get_tool_size("pointer") if self.controller else 18
        self.pointer_radius = max(12.0, base_dim * (pointer_size * 0.001))

        r = self.pointer_radius
        self.pointer_item.setRect(-r, -r, r * 2, r * 2)

        # 視認性の高い発光レーザーグラデーション
        gradient = QRadialGradient(0, 0, r)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 255))   # 中心核（眩しい白）
        gradient.setColorAt(0.25, QColor(255, 60, 60, 240))    # 高輝度赤
        gradient.setColorAt(0.65, QColor(220, 0, 0, 180))     # 鮮烈な赤
        gradient.setColorAt(1.0, QColor(200, 0, 0, 0))         # 外側のぼかしフェード

        self.pointer_item.setBrush(QBrush(gradient))
        self.pointer_item.setVisible(False)

    def _clear_scene_strokes(self):
        """シーンから描画ストロークアイテムのみを安全に削除"""
        for item in self.stroke_items:
            try:
                self.scene.removeItem(item)
            except RuntimeError:
                pass
        self.stroke_items.clear()
        self.active_path_item = None
        self.active_path = None

    def _clear_scene_texts(self):
        """シーンからテキストアイテムのみを安全に削除"""
        for item in self.text_items:
            try:
                self.scene.removeItem(item)
            except RuntimeError:
                pass
        self.text_items.clear()

    def show_image(self, image: QPixmap) -> None:
        self.page_pixmap = image

        # 既存ストロークおよびテキストのみ削除（シーン全体を clear して C++ オブジェクトを破棄しない）
        self._clear_scene_strokes()
        self._clear_scene_texts()

        # ピックスマップ更新
        self.pixmap_item.setPixmap(self.page_pixmap)
        self.scene.setSceneRect(QRectF(self.page_pixmap.rect()))

        # スライド解像度に合わせたポインタサイズ・グラデーション更新
        self._setup_pointer_item()

        # 既存ストローク・テキストの復元
        if self.controller:
            page_strokes = self.controller.get_strokes_for_page(self.controller.current_page)
            for stroke in page_strokes:
                self._draw_complete_stroke(stroke)
            page_texts = self.controller.get_texts_for_page(self.controller.current_page)
            for t_item in page_texts:
                self._draw_complete_text(t_item)

        self.fit_view()

    def _draw_complete_stroke(self, stroke: Stroke):
        if not self.page_pixmap or not stroke.points:
            return
        
        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        base_dim = min(w, h)
        pen_width = max(2.5, base_dim * stroke.width_ratio)

        color = QColor(stroke.color)
        color.setAlphaF(stroke.opacity)
        pen = QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        path = QPainterPath()
        p0 = stroke.points[0]
        path.moveTo(p0[0] * w, p0[1] * h)
        for pt in stroke.points[1:]:
            path.lineTo(pt[0] * w, pt[1] * h)

        path_item = self.scene.addPath(path, pen)
        path_item.setZValue(10)
        self.stroke_items.append(path_item)

    def _draw_complete_text(self, item: TextItem):
        if not self.page_pixmap or not item.text:
            return
        
        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        base_dim = min(w, h)
        font_size = max(10, int(base_dim * (item.size * 0.0015)))

        font = QFont()
        font.setPixelSize(font_size)
        font.setBold(False)
        font.setWeight(QFont.Weight.Normal)

        text_item = QGraphicsSimpleTextItem(item.text)
        text_item.setFont(font)
        text_item.setBrush(QBrush(QColor(item.color)))
        text_item.setPen(QPen(Qt.PenStyle.NoPen))
        
        pad_x = 6.0 * (w / 800.0) if w > 0 else 6.0
        pad_y = 3.0 * (h / 600.0) if h > 0 else 3.0
        text_item.setPos(item.norm_x * w + pad_x, item.norm_y * h + pad_y)
        text_item.setZValue(20)  # ストロークの上に配置
        self.scene.addItem(text_item)
        self.text_items.append(text_item)

    def on_pointer_updated(self, norm_x: float, norm_y: float, visible: bool):
        if not self.pointer_item:
            return
        if not visible or not self.page_pixmap or self.is_blank:
            self.pointer_item.setVisible(False)
            return

        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        self.pointer_item.setPos(norm_x * w, norm_y * h)
        self.pointer_item.setVisible(True)

    def on_stroke_started(self, page_index: int, stroke: Stroke):
        if not self.page_pixmap or (self.controller and page_index != self.controller.current_page):
            return
        
        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        base_dim = min(w, h)
        pen_width = max(2.5, base_dim * stroke.width_ratio)

        color = QColor(stroke.color)
        color.setAlphaF(stroke.opacity)
        pen = QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        self.active_path = QPainterPath()
        p0 = stroke.points[0]
        self.active_path.moveTo(p0[0] * w, p0[1] * h)

        self.active_path_item = self.scene.addPath(self.active_path, pen)
        self.active_path_item.setZValue(10)
        self.stroke_items.append(self.active_path_item)

    def on_stroke_added_point(self, page_index: int, norm_x: float, norm_y: float, pressure: float = 1.0):
        if not self.page_pixmap or self.active_path is None or self.active_path_item is None:
            return
        if self.controller and page_index != self.controller.current_page:
            return

        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        self.active_path.lineTo(norm_x * w, norm_y * h)
        self.active_path_item.setPath(self.active_path)

    def on_stroke_line_updated(self, page_index: int, norm_x: float, norm_y: float):
        """直線の終点ドラッグ中プレビュー更新"""
        if not self.page_pixmap or self.active_path_item is None or not self.controller:
            return
        if page_index != self.controller.current_page:
            return

        w = self.page_pixmap.width()
        h = self.page_pixmap.height()
        if self.controller.current_stroke and self.controller.current_stroke.points:
            p0 = self.controller.current_stroke.points[0]
            new_path = QPainterPath()
            new_path.moveTo(p0[0] * w, p0[1] * h)
            new_path.lineTo(norm_x * w, norm_y * h)
            self.active_path = new_path
            self.active_path_item.setPath(self.active_path)

    def on_tool_size_changed(self, tool_name: str, size: int):
        if tool_name == "pointer":
            self._setup_pointer_item()

    def on_stroke_finished(self, page_index: int):
        self.active_path = None
        self.active_path_item = None

    def on_strokes_cleared(self, page_index: int):
        self._clear_scene_strokes()
        self._clear_scene_texts()

    def on_stroke_undone(self, page_index: int):
        if self.stroke_items:
            last_item = self.stroke_items.pop()
            try:
                self.scene.removeItem(last_item)
            except RuntimeError:
                pass

    def on_text_added(self, page_index: int, item: TextItem):
        if not self.page_pixmap or (self.controller and page_index != self.controller.current_page):
            return
        self._draw_complete_text(item)

    def on_texts_updated(self, page_index: int):
        if not self.page_pixmap or (self.controller and page_index != self.controller.current_page):
            return
        self._clear_scene_texts()
        if self.controller:
            page_texts = self.controller.get_texts_for_page(page_index)
            for t_item in page_texts:
                self._draw_complete_text(t_item)

    def on_strokes_updated(self, page_index: int):
        """消しゴム等でストロークが変更されたときの全ストローク再描画"""
        if not self.page_pixmap:
            return
        self._clear_scene_strokes()

        if self.controller:
            page_strokes = self.controller.get_strokes_for_page(page_index)
            for stroke in page_strokes:
                self._draw_complete_stroke(stroke)

    def fit_view(self):
        if self.page_pixmap and not self.scene.sceneRect().isEmpty():
            self.graphics_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.fit_view()
        if self.is_blank:
            self.blank_overlay.setGeometry(self.rect())

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_blank(self):
        """ブランクスクリーン（ウィンドウを維持したまま全画面を真っ黒にする）"""
        self.is_blank = not self.is_blank
        if self.is_blank:
            self.blank_overlay.setGeometry(self.rect())
            self.blank_overlay.show()
            self.blank_overlay.raise_()
            if self.pointer_item:
                self.pointer_item.setVisible(False)
        else:
            self.blank_overlay.hide()
        self.blank_state_changed.emit(self.is_blank)

    def blank_screen(self):
        self.toggle_blank()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_F5, Qt.Key.Key_F11):
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif key == Qt.Key.Key_B:
            self.toggle_blank()
        elif self.controller:
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
                self.controller.next_page()
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
                self.controller.prev_page()
        super().keyPressEvent(event)
