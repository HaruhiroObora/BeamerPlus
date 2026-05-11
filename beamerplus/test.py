import sys
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView


class MainWindow(QMainWindow):
    def __init__(self, pdf_path: str):
        super().__init__()

        self.setWindowTitle("BeamerPlus")

        #
        # PDF document
        #
        self.document = QPdfDocument(self)

        error = self.document.load(pdf_path)

        if error != QPdfDocument.Error.None_:
            raise RuntimeError(
                f"Failed to load PDF: {pdf_path}\n"
                f"Error: {error}"
            )

        #
        # PDF view
        #
        self.view = QPdfView(self)

        self.view.setDocument(self.document)

        # 単ページ表示
        self.view.setPageMode(QPdfView.PageMode.SinglePage)

        # ウィンドウにフィット
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)

        self.view.scro

        self.setCentralWidget(self.view)

        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        #
        # current page
        #
        self.current_page = 0

        self.update_page()

    def update_page(self):
        self.view.pageNavigator().jump(
            self.current_page,
            QPointF(0, 0),
        )

    def next_page(self):
        if self.current_page < self.document.pageCount() - 1:
            self.current_page += 1
            self.update_page()

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        key = event.key()

        #
        # next page
        #
        if key in (
            Qt.Key.Key_Right,
            Qt.Key.Key_Down,
            Qt.Key.Key_Space,
            Qt.Key.Key_PageDown,
        ):
            self.next_page()

        #
        # previous page
        #
        elif key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Up,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_PageUp,
        ):
            self.previous_page()

        #
        # fullscreen
        #
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()

        #
        # quit
        #
        elif key == Qt.Key.Key_Escape:
            self.close()

        else:
            super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)

    #
    # main.py と同じ場所の slides.pdf
    #
    pdf_path = Path(__file__).parent / "slides.pdf"

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found:\n{pdf_path}"
        )

    window = MainWindow(str(pdf_path))

    window.resize(1280, 720)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()