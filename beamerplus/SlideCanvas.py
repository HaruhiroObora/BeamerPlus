import math
from PySide6.QtCore import Qt, QPointF, QRectF, QEvent
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPixmap, QPainter, QPaintEvent, QMouseEvent, QTabletEvent,
    QPointingDevice, QColor, QPen, QPainterPath, QRadialGradient, QBrush
)

from beamerplus.DrawingModel import PresentationController, Stroke


class SlideCanvas(QWidget):
    def __init__(self, controller: PresentationController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.pixmap: QPixmap | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background-color: #121212;")

        # コントローラシグナル接続
        self.controller.pointer_updated.connect(self._on_pointer_updated)
        self.controller.stroke_started.connect(self._on_stroke_started)
        self.controller.stroke_added_point.connect(self._on_stroke_added_point)
        self.controller.stroke_line_updated.connect(self._on_stroke_line_updated)
        self.controller.stroke_finished.connect(self._on_stroke_finished)
        self.controller.strokes_cleared.connect(self._on_strokes_cleared)
        self.controller.stroke_undone.connect(self._on_stroke_undone)
        self.controller.strokes_updated.connect(self._on_strokes_updated)
        self.controller.tool_size_changed.connect(self._on_tool_size_changed)
        self.controller.line_mode_changed.connect(self._on_line_mode_changed)
        self.controller.eraser_mode_changed.connect(self._on_eraser_mode_changed)
        self.controller.color_changed.connect(self._on_color_changed)

        self.pointer_pos: tuple[float, float] | None = None
        self.is_pointer_visible: bool = False

        # Wacom / タブレット用状態
        self.is_tablet_drawing: bool = False
        self.hover_pos: tuple[float, float] | None = None

    def set_pixmap(self, pixmap: QPixmap | None):
        self.pixmap = pixmap
        self.update()

    def _get_slide_rect(self) -> QRectF:
        if not self.pixmap or self.pixmap.isNull():
            return QRectF()
        
        w = self.width()
        h = self.height()
        pw = self.pixmap.width()
        ph = self.pixmap.height()

        if pw == 0 or ph == 0:
            return QRectF()

        scale = min(w / pw, h / ph)
        target_w = pw * scale
        target_h = ph * scale
        x = (w - target_w) / 2.0
        y = (h - target_h) / 2.0
        return QRectF(x, y, target_w, target_h)

    def _pos_to_normalized(self, pos: QPointF) -> tuple[float, float] | None:
        rect = self._get_slide_rect()
        if rect.isEmpty():
            return None
        
        norm_x = (pos.x() - rect.left()) / rect.width()
        norm_y = (pos.y() - rect.top()) / rect.height()

        if 0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0:
            return (norm_x, norm_y)
        return None

    def _snap_line_endpoint(self, end_norm: tuple[float, float]) -> tuple[float, float]:
        """水平・垂直方向（±5度以内）の自動スナップ補正"""
        if not self.controller.current_stroke or not self.controller.current_stroke.points:
            return end_norm

        p0 = self.controller.current_stroke.points[0]
        x0, y0 = p0[0], p0[1]
        x1, y1 = end_norm

        rect = self._get_slide_rect()
        if rect.isEmpty():
            return end_norm

        # 画面ピクセル基準での差分
        dx_px = (x1 - x0) * rect.width()
        dy_px = (y1 - y0) * rect.height()

        dist_px = math.hypot(dx_px, dy_px)
        if dist_px < 8.0:
            return end_norm

        # 角度判定 (0 ~ 90度)
        angle_deg = math.degrees(math.atan2(abs(dy_px), abs(dx_px)))
        SNAP_DEG = 5.0

        if angle_deg <= SNAP_DEG:
            # 水平線にスナップ（Y座標を始点と同一にする）
            return (x1, y0)
        elif angle_deg >= (90.0 - SNAP_DEG):
            # 垂直線にスナップ（X座標を始点と同一にする）
            return (x0, y1)

        return end_norm

    def _on_pointer_updated(self, nx: float, ny: float, visible: bool):
        self.is_pointer_visible = visible
        if visible:
            self.pointer_pos = (nx, ny)
        self.update()

    def _on_stroke_started(self, page_index: int, stroke: Stroke):
        self.update()

    def _on_stroke_added_point(self, page_index: int, nx: float, ny: float, pressure: float):
        self.update()

    def _on_stroke_line_updated(self, page_index: int, nx: float, ny: float):
        self.update()

    def _on_stroke_finished(self, page_index: int):
        self.update()

    def _on_strokes_cleared(self, page_index: int):
        self.update()

    def _on_stroke_undone(self, page_index: int):
        self.update()

    def _on_strokes_updated(self, page_index: int):
        self.update()

    def _on_tool_size_changed(self, tool_name: str, size: int):
        self.update()

    def _on_line_mode_changed(self, is_line: bool):
        self.update()

    def _on_eraser_mode_changed(self, mode: str):
        self.update()

    def _on_color_changed(self, tool_name: str, color: str):
        self.update()

    # ==========================================
    # Wacom / スタイラスペン入力イベント処理
    # ==========================================
    def tabletEvent(self, event: QTabletEvent):
        norm = self._pos_to_normalized(event.position())
        device = event.pointingDevice()
        is_eraser = device is not None and device.pointerType() == QPointingDevice.PointerType.Eraser
        pressure = event.pressure()
        tool = self.controller.current_tool
        ev_type = event.type()

        # 1. 消しゴム機能（ペン尻 または 消しゴムツール選択時）
        if is_eraser or tool == "eraser":
            rect = self._get_slide_rect()
            aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
            eraser_size = self.controller.get_tool_size("eraser")
            threshold = max(0.008, eraser_size * 0.001)

            if pressure > 0.0 and norm is not None:
                self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
            self.hover_pos = norm
            self.update()
            event.accept()
            return

        # 2. レーザーポインタモード（ホバーでもなぞってもポインタとして機能）
        if tool == "pointer":
            if norm is not None:
                self.controller.update_pointer(norm[0], norm[1], True)
            else:
                self.controller.update_pointer(0, 0, False)
            event.accept()
            return

        # 3. 描画ツール（ペン / 蛍光ペン）
        if tool in ("pen", "highlighter"):
            if ev_type == QEvent.Type.TabletPress:
                if norm is not None and pressure > 0.0:
                    self.is_tablet_drawing = True
                    self.hover_pos = None
                    self.controller.begin_stroke(norm[0], norm[1], pressure=pressure)

            elif ev_type == QEvent.Type.TabletMove:
                if pressure > 0.0 and norm is not None:
                    # なぞっている最中
                    if not self.is_tablet_drawing:
                        self.is_tablet_drawing = True
                        self.controller.begin_stroke(norm[0], norm[1], pressure=pressure)
                    else:
                        if self.controller.is_line_mode:
                            snapped = self._snap_line_endpoint(norm)
                            self.controller.update_line_endpoint(snapped[0], snapped[1], pressure=pressure)
                        else:
                            self.controller.add_stroke_point(norm[0], norm[1], pressure=pressure)
                    self.hover_pos = None
                else:
                    # ホバー中
                    if self.is_tablet_drawing:
                        self.is_tablet_drawing = False
                        self.controller.end_stroke()
                    self.hover_pos = norm
                    self.update()

            elif ev_type == QEvent.Type.TabletRelease:
                if self.is_tablet_drawing:
                    self.is_tablet_drawing = False
                    self.controller.end_stroke()
                self.hover_pos = norm
                self.update()

            event.accept()
            return

        # 4. 通常モード（ハンドツール）
        if tool == "hand":
            if ev_type == QEvent.Type.TabletPress and norm is not None:
                if event.button() == Qt.MouseButton.RightButton:
                    self.controller.prev_page()
                else:
                    self.controller.next_page()
            event.accept()
            return

        super().tabletEvent(event)

    # ==========================================
    # 通常マウス操作
    # ==========================================
    def mousePressEvent(self, event: QMouseEvent):
        norm = self._pos_to_normalized(event.position())
        if not norm:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            tool = self.controller.current_tool
            if tool in ("pen", "highlighter"):
                self.controller.begin_stroke(norm[0], norm[1], pressure=1.0)
            elif tool == "eraser":
                rect = self._get_slide_rect()
                aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
                eraser_size = self.controller.get_tool_size("eraser")
                threshold = max(0.008, eraser_size * 0.001)
                self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
            elif tool == "hand":
                self.controller.next_page()
            elif tool == "pointer":
                self.controller.update_pointer(norm[0], norm[1], True)
        elif event.button() == Qt.MouseButton.RightButton:
            self.controller.prev_page()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        norm = self._pos_to_normalized(event.position())
        tool = self.controller.current_tool

        if norm:
            if tool == "pointer":
                self.controller.update_pointer(norm[0], norm[1], True)
            elif tool == "eraser":
                if event.buttons() & Qt.MouseButton.LeftButton:
                    rect = self._get_slide_rect()
                    aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
                    eraser_size = self.controller.get_tool_size("eraser")
                    threshold = max(0.008, eraser_size * 0.001)
                    self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
                self.hover_pos = norm
                self.update()
            elif tool in ("pen", "highlighter"):
                if event.buttons() & Qt.MouseButton.LeftButton:
                    if self.controller.is_line_mode:
                        snapped = self._snap_line_endpoint(norm)
                        self.controller.update_line_endpoint(snapped[0], snapped[1], pressure=1.0)
                    else:
                        self.controller.add_stroke_point(norm[0], norm[1], pressure=1.0)
                    self.hover_pos = None
                else:
                    self.hover_pos = norm
                    self.update()
        else:
            if tool == "pointer":
                self.controller.update_pointer(0, 0, False)
            self.hover_pos = None
            self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            tool = self.controller.current_tool
            if tool in ("pen", "highlighter"):
                self.controller.end_stroke()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self.controller.current_tool == "pointer":
            self.controller.update_pointer(0, 0, False)
        self.hover_pos = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 背景塗りつぶし
        painter.fillRect(self.rect(), QColor("#121212"))

        rect = self._get_slide_rect()
        if not self.pixmap or rect.isEmpty():
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "スライドが読み込まれていません")
            return

        # スライド画像描画
        painter.drawPixmap(rect.toRect(), self.pixmap)

        # ストローク描画
        strokes = self.controller.get_strokes_for_page(self.controller.current_page)
        base_dim = min(rect.width(), rect.height())

        for stroke in strokes:
            if not stroke.points:
                continue
            color = QColor(stroke.color)
            color.setAlphaF(stroke.opacity)
            pen_w = max(1.5, base_dim * stroke.width_ratio)
            pen = QPen(color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)

            path = QPainterPath()
            p0 = stroke.points[0]
            path.moveTo(rect.left() + p0[0] * rect.width(), rect.top() + p0[1] * rect.height())
            for pt in stroke.points[1:]:
                path.lineTo(rect.left() + pt[0] * rect.width(), rect.top() + pt[1] * rect.height())
            painter.drawPath(path)

        # 消しゴムカーソル（手元画面のみ、消去範囲を示す円）
        if self.controller.current_tool == "eraser" and self.hover_pos:
            hx = rect.left() + self.hover_pos[0] * rect.width()
            hy = rect.top() + self.hover_pos[1] * rect.height()
            size = self.controller.get_tool_size("eraser")
            eraser_r = max(6.0, base_dim * (size * 0.001))

            if self.controller.eraser_mode == "partial":
                # 通常消しゴム: くり抜く範囲を示す実線円＋半透明塗り
                eraser_pen = QPen(QColor(255, 120, 120, 240), 1.5, Qt.PenStyle.SolidLine)
                painter.setPen(eraser_pen)
                painter.setBrush(QBrush(QColor(255, 100, 100, 45)))
            else:
                # オブジェクト消しゴム: 接触判定を示す点線円
                eraser_pen = QPen(QColor(255, 160, 160, 200), 1.2, Qt.PenStyle.DashLine)
                painter.setPen(eraser_pen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 20)))

            painter.drawEllipse(QPointF(hx, hy), eraser_r, eraser_r)

        # ホバー時カーソル（手元画面のみ、ペン先の位置・太さを示すペンの色で塗りつぶした丸）
        if self.controller.current_tool in ("pen", "highlighter") and self.hover_pos:
            hx = rect.left() + self.hover_pos[0] * rect.width()
            hy = rect.top() + self.hover_pos[1] * rect.height()
            current_size = self.controller.get_current_tool_size()
            curr_r = max(3.0, (base_dim * (current_size * 0.001)) / 2.0)

            tool_color = self.controller.get_tool_color(self.controller.current_tool)
            fill_color = QColor(tool_color)
            if self.controller.current_tool == "highlighter":
                # 蛍光ペン: 文字を隠さない適度な透明度＋輪郭線
                fill_color.setAlphaF(0.65)
                border_color = QColor(tool_color).darker(120)
                border_color.setAlphaF(0.9)
            else:
                # 通常ペン: ペンの色でしっかり塗りつぶし
                fill_color.setAlphaF(0.9)
                border_color = QColor(tool_color).darker(115)
                border_color.setAlphaF(1.0)

            painter.setPen(QPen(border_color, 1.2, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(fill_color))
            painter.drawEllipse(QPointF(hx, hy), curr_r, curr_r)

        # レーザーポインタ描画
        if self.is_pointer_visible and self.pointer_pos:
            px = rect.left() + self.pointer_pos[0] * rect.width()
            py = rect.top() + self.pointer_pos[1] * rect.height()
            pointer_size = self.controller.get_tool_size("pointer")
            radius = max(8.0, base_dim * (pointer_size * 0.001))

            gradient = QRadialGradient(px, py, radius)
            gradient.setColorAt(0.0, QColor(255, 255, 255, 255))
            gradient.setColorAt(0.25, QColor(255, 60, 60, 240))
            gradient.setColorAt(0.65, QColor(220, 0, 0, 180))
            gradient.setColorAt(1.0, QColor(200, 0, 0, 0))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawEllipse(QPointF(px, py), radius, radius)
