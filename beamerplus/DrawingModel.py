from dataclasses import dataclass, field
import math
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor


@dataclass
class Stroke:
    color: str = "#e53935"       # HEX または色文字列
    width_ratio: float = 0.005   # 画像の短辺に対する比率
    opacity: float = 0.85
    # (norm_x, norm_y, pressure): pressure は 0.0 ~ 1.0 (マウス時は1.0)
    points: list[tuple[float, float, float]] = field(default_factory=list)


class PresentationController(QObject):
    """
    スライド状態、描画ストローク、ポインタ位置、ツール設定を一括管理し、
    MainWindow と Viewer の間で同期を行うコントローラ
    """
    # ページ変更
    page_changed = Signal(int)

    # ポインタ同期 (0.0 ~ 1.0)
    pointer_updated = Signal(float, float, bool)  # norm_x, norm_y, visible

    # 描画ストローク同期
    stroke_started = Signal(int, Stroke)                  # page_index, new_stroke
    stroke_added_point = Signal(int, float, float, float)  # page_index, norm_x, norm_y, pressure
    stroke_line_updated = Signal(int, float, float)       # page_index, norm_x, norm_y (直線プレビュー更新)
    stroke_finished = Signal(int)                         # page_index
    strokes_cleared = Signal(int)                         # page_index
    stroke_undone = Signal(int)                           # page_index
    strokes_updated = Signal(int)                         # page_index (消しゴム等での再描画)

    # ツールモード変更
    tool_changed = Signal(str)                            # "hand", "pointer", "pen", "highlighter", "eraser"
    tool_size_changed = Signal(str, int)                  # tool_name, size (1 ~ 50)
    color_changed = Signal(str, str)                      # tool_name, hex_color
    line_mode_changed = Signal(bool)                      # 直線モードのON/OFF

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.current_page: int = 0
        self.total_pages: int = 0
        self.current_tool: str = "hand"  # 起動時は通常モード ("hand", "pointer", "pen", "highlighter", "eraser")
        self.is_line_mode: bool = False  # 直線モードON/OFF（pen / highlighter 時に直線を描画）
        
        # ページごとのストローク保存: dict[page_index, list[Stroke]]
        self.page_strokes: dict[int, list[Stroke]] = {}
        self.current_stroke: Stroke | None = None

        # 各ツールのサイズ（太さ / 半径）設定 (スライダ値: 1 ~ 50)
        # width_ratio = size * 0.001
        self.tool_sizes: dict[str, int] = {
            "pointer": 18,      # 半径比率: 0.018 (短辺の1.8%)
            "pen": 5,          # 線幅比率: 0.005 (短辺の0.5%)
            "highlighter": 15,  # 線幅比率: 0.015 (短辺の1.5%)
            "eraser": 20,       # 消去判定半径比率: 0.020 (短辺の2.0%)
        }

        # 色設定
        self.pen_color: str = "#e53935"            # ペンの色（デフォルト赤）
        self.highlighter_color: str = "#ffeb3b"    # 蛍光ペンの色（デフォルト蛍光イエロー）

    def set_total_pages(self, total: int):
        self.total_pages = total

    def set_page(self, index: int):
        if self.total_pages > 0 and 0 <= index < self.total_pages:
            if self.current_page != index:
                self.current_page = index
                self.pointer_updated.emit(0.0, 0.0, False)
                self.page_changed.emit(index)

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.set_page(self.current_page + 1)

    def prev_page(self):
        if self.current_page > 0:
            self.set_page(self.current_page - 1)

    def set_tool(self, tool_name: str):
        if tool_name in ("hand", "pointer", "eraser"):
            # 通常モードやポインタ、消しゴムに切り替えた場合は直線モードを解除
            self.set_line_mode(False)

        if tool_name != self.current_tool:
            self.current_tool = tool_name
            self.tool_changed.emit(tool_name)
            if tool_name != "pointer":
                self.pointer_updated.emit(0.0, 0.0, False)

    def set_line_mode(self, enabled: bool):
        if self.is_line_mode != enabled:
            self.is_line_mode = enabled
            self.line_mode_changed.emit(enabled)

    def toggle_line_mode(self):
        # ポインタや通常モード、消しゴム時に直線ボタンが押されたら、デフォルトでペンを選択した上で直線モードへ
        if self.current_tool not in ("pen", "highlighter"):
            self.set_tool("pen")
            self.set_line_mode(True)
        else:
            self.set_line_mode(not self.is_line_mode)

    def get_tool_size(self, tool_name: str) -> int:
        return self.tool_sizes.get(tool_name, 5)

    def set_tool_size(self, tool_name: str, size: int):
        clamped_size = max(1, min(50, size))
        self.tool_sizes[tool_name] = clamped_size
        self.tool_size_changed.emit(tool_name, clamped_size)

    def get_current_tool_size(self) -> int:
        return self.get_tool_size(self.current_tool)

    def set_current_tool_size(self, size: int):
        self.set_tool_size(self.current_tool, size)

    def get_tool_color(self, tool_name: str) -> str:
        if tool_name == "highlighter":
            return self.highlighter_color
        return self.pen_color

    def set_tool_color(self, tool_name: str, hex_color: str):
        if tool_name == "highlighter":
            self.highlighter_color = hex_color
        else:
            self.pen_color = hex_color
        self.color_changed.emit(tool_name, hex_color)

    def update_pointer(self, norm_x: float, norm_y: float, visible: bool):
        self.pointer_updated.emit(norm_x, norm_y, visible)

    def begin_stroke(self, norm_x: float, norm_y: float, pressure: float = 1.0):
        if self.current_tool not in ("pen", "highlighter"):
            return
        
        size = self.get_tool_size(self.current_tool)
        width_ratio = size * 0.001

        if self.current_tool == "highlighter":
            color = self.highlighter_color
            opacity = 0.45
        else:
            color = self.pen_color
            opacity = 0.85

        stroke = Stroke(color=color, width_ratio=width_ratio, opacity=opacity, points=[(norm_x, norm_y, pressure)])
        self.current_stroke = stroke
        if self.current_page not in self.page_strokes:
            self.page_strokes[self.current_page] = []
        self.page_strokes[self.current_page].append(stroke)
        self.stroke_started.emit(self.current_page, stroke)

    def add_stroke_point(self, norm_x: float, norm_y: float, pressure: float = 1.0):
        if self.current_stroke is not None:
            self.current_stroke.points.append((norm_x, norm_y, pressure))
            self.stroke_added_point.emit(self.current_page, norm_x, norm_y, pressure)

    def update_line_endpoint(self, norm_x: float, norm_y: float, pressure: float = 1.0):
        """直線ツールドラッグ中に終点をリアルタイム更新"""
        if self.current_stroke is not None and len(self.current_stroke.points) >= 1:
            p0 = self.current_stroke.points[0]
            self.current_stroke.points = [p0, (norm_x, norm_y, pressure)]
            self.stroke_line_updated.emit(self.current_page, norm_x, norm_y)

    def end_stroke(self):
        if self.current_stroke is not None:
            self.current_stroke = None
            self.stroke_finished.emit(self.current_page)

    def erase_strokes_near(self, norm_x: float, norm_y: float, threshold: float = 0.02) -> bool:
        """指定された相対座標の近くにあるストロークを消去"""
        if self.current_page not in self.page_strokes or not self.page_strokes[self.current_page]:
            return False

        remaining_strokes = []
        erased = False

        for stroke in self.page_strokes[self.current_page]:
            hit = False
            for pt in stroke.points:
                dx = pt[0] - norm_x
                dy = pt[1] - norm_y
                if math.hypot(dx, dy) < threshold:
                    hit = True
                    break
            if hit:
                erased = True
            else:
                remaining_strokes.append(stroke)

        if erased:
            self.page_strokes[self.current_page] = remaining_strokes
            self.strokes_updated.emit(self.current_page)
            return True
        return False

    def clear_current_page_strokes(self):
        if self.current_page in self.page_strokes:
            self.page_strokes[self.current_page] = []
            self.strokes_cleared.emit(self.current_page)

    def undo_current_page_stroke(self):
        if self.current_page in self.page_strokes and self.page_strokes[self.current_page]:
            self.page_strokes[self.current_page].pop()
            self.stroke_undone.emit(self.current_page)

    def get_strokes_for_page(self, page_index: int) -> list[Stroke]:
        return self.page_strokes.get(page_index, [])
