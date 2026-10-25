import os.path
import json

import pymupdf

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QImage, QPixmap

CROP_THRESHOLD = 2.5
DEFAULT_DPI = 400  # デフォルト解像度 (4Kディスプレイでも一切ボケない超高精細DPI)


class PdfReader:
    def __init__(self, path: str):
        self.path = path
        self.note_path = path + ".json"
        try:
            self.document = pymupdf.open(self.path)
            if os.path.exists(self.note_path):
                with open(self.note_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.notes: dict[int, str] = {int(k): v for k, v in data.items()}
            else:
                self.notes: dict[int, str] = {}
        except Exception as e:
            raise e
        
        self.page_labels = [i.get_label() for i in self.document]
        self._image_cache: dict[tuple[int, int, bool], QPixmap] = {}

    @property
    def page_count(self) -> int:
        return len(self.document)

    def __len__(self) -> int:
        return len(self.document)

    def _resolve_index(self, index: str | int) -> int | None:
        if isinstance(index, int):
            if 0 <= index < len(self.document):
                return index
            return None
        elif isinstance(index, str):
            try:
                return self.page_labels.index(index)
            except ValueError:
                return None
        return None

    def get_page_image(
        self, index: str | int, auto_crop: bool = True, size: QSize | None = None, dpi: int = DEFAULT_DPI
    ) -> QPixmap | None:
        idx = self._resolve_index(index)
        if idx is None:
            return None

        # 原寸画像をキャッシュ (key: page_idx, dpi, auto_crop)
        cache_key = (idx, dpi, auto_crop)
        if cache_key in self._image_cache:
            pixmap = self._image_cache[cache_key]
        else:
            page = self.document[idx]
            pixmap = self.page_to_image(page, auto_crop=auto_crop, size=None, dpi=dpi)
            if pixmap is not None:
                self._image_cache[cache_key] = pixmap

        if pixmap is None:
            return None

        if size is not None:
            return pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return pixmap

    def get_page(self, index: str | int) -> pymupdf.Page | None:
        idx = self._resolve_index(index)
        if idx is None:
            return None
        return self.document[idx]

    def get_note(self, index: str | int) -> str | None:
        idx = self._resolve_index(index)
        if idx is None:
            return None
        return self.notes.get(idx, "")

    def is_dual_screen_page(self, index: str | int) -> bool:
        """ページが左右または上下の2画面（スライド＋ノート）形式か判定"""
        page = self.get_page(index)
        if page is None:
            return False
        rect = page.rect
        # 左右2画面 (show notes on second screen=right など)
        if rect.width > rect.height * 2.0:
            return True
        # 上下2画面 (show notes on second screen=bottom など)
        if rect.height > rect.width * 1.1:
            return True
        return False

    def get_embedded_note_image(
        self, index: str | int, size: QSize | None = None, dpi: int = DEFAULT_DPI
    ) -> QPixmap | None:
        """
        2画面レイアウトの場合、ノート側の高精細レンダリング画像を取得する
        """
        idx = self._resolve_index(index)
        if idx is None:
            return None

        cache_key = (idx, dpi, "note_image")
        if cache_key in self._image_cache:
            pixmap = self._image_cache[cache_key]
        else:
            page = self.document[idx]
            rect = page.rect
            if rect.width > rect.height * 2.0:
                notes_clip = pymupdf.Rect(rect.width / 2.0, 0, rect.width, rect.height)
            elif rect.height > rect.width * 1.1:
                notes_clip = pymupdf.Rect(0, rect.height / 2.0, rect.width, rect.height)
            else:
                return None

            pix = page.get_pixmap(clip=notes_clip, dpi=dpi)
            fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            pixmap = QPixmap.fromImage(qimage)
            self._image_cache[cache_key] = pixmap

        if size is not None and pixmap is not None:
            return pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return pixmap

    def has_embedded_note(self, index: str | int) -> bool:
        """指定ページに埋め込みノート画面が存在するか（2画面レイアウト判定）"""
        return self.is_dual_screen_page(index)

    def save_note(self, index: str | int, note: str) -> None:
        idx = self._resolve_index(index)
        if idx is None:
            return
        self.notes[idx] = note

    def save_note_to_file(self) -> None:
        try:
            with open(self.note_path, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise e

    def search_page(self, keyword: str) -> list[pymupdf.Page]:
        pages: list[pymupdf.Page] = []
        for i, label in enumerate(self.page_labels):
            if keyword in label.lower():
                pages.append(self.document[i])
        return pages

    def clear_cache(self):
        self._image_cache.clear()

    @classmethod
    def page_to_image(
        cls, page: pymupdf.Page, auto_crop: bool = True, size: QSize | None = None, dpi: int = DEFAULT_DPI
    ) -> QPixmap | None:
        pix = page.get_pixmap(dpi=dpi)
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        if auto_crop:
            # 左右2画面形式 (show notes on second screen=right) -> 左半分がスライド
            if pix.width > pix.height * 2.0:
                qimage = qimage.copy(QRect(0, 0, qimage.width() // 2, qimage.height()))
            # 上下2画面形式 (show notes on second screen=bottom) -> 上半分がスライド
            elif pix.height > pix.width * 1.1:
                qimage = qimage.copy(QRect(0, 0, qimage.width(), qimage.height() // 2))

        if size is None:
            qpixmap = QPixmap.fromImage(qimage)
        else:
            qpixmap = QPixmap.fromImage(qimage.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        return qpixmap
