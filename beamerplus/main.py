import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from beamerplus.MainWindow import MainWindow
from beamerplus.Viewer import Viewer


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BeamerPlus")

    # Viewer（プロジェクタ用画面）と MainWindow（発表者画面）のインスタンス生成
    viewer = Viewer()
    main_window = MainWindow(viewer=viewer)

    # マルチモニターのチェックと配置
    screens = app.screens()
    if len(screens) > 1:
        # 2番目の画面がある場合はViewerをそちらに配置して全画面表示
        second_screen = screens[1]
        geom = second_screen.geometry()
        viewer.setGeometry(geom)
        viewer.show()
        viewer.showFullScreen()

        # メイン画面に発表者ウィンドウを配置
        main_window.setGeometry(screens[0].geometry().adjusted(50, 50, -50, -50))
        main_window.show()
    else:
        # 単一画面の場合は両方をウィンドウ表示
        viewer.resize(800, 600)
        viewer.show()
        main_window.show()

    # コマンドライン引数にPDFが指定されていたら自動でロード
    pdf_path = None
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        pdf_path = sys.argv[1]

    if pdf_path and os.path.exists(pdf_path):
        main_window.load_pdf(pdf_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
