from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QGraphicsView, QGraphicsScene
from PySide6.QtGui import QPixmap, QPainter, QResizeEvent

class Viewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BeamerPlus プロジェクタ")

        self.graphics_view = QGraphicsView()
        self.setCentralWidget(self.graphics_view)
        self.graphics_view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.graphics_view.setStyleSheet("background-color: black; border: none;")

        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.scene = QGraphicsScene(self)
        self.graphics_view.setScene(self.scene)

        self.page_pixmap:QPixmap | None = None

    def show_image(self, image:QPixmap) -> None:
        self.page_pixmap = image
        self.scene.clear()
        self.scene.addPixmap(self.page_pixmap)
        self.scene.setSceneRect(self.page_pixmap.rect())

        self.fit_view()

    def fit_view(self):
        if self.page_pixmap:
            self.graphics_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def resizeEvent(self, event:QResizeEvent):
        super().resizeEvent(event)
        self.fit_view()
    
    def blank_screen(self):
        self.scene.clear()
    
    def get_scene(self) -> QGraphicsScene:
        return self.scene