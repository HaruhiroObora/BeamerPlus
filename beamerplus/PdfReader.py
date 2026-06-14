import os.path
import pickle
import json

import fitz

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QImage, QPixmap

CROP_THRESHOLD = 2.5

class PdfReader:
    def __init__(self, path:str):
        self.path = path
        self.note_path = path + ".json"
        try:
            self.document = fitz.open(self.path)
            if os.path.exists(self.note_path):
                with open(self.note_path, "r") as f:
                    self.notes:dict[int, str] = json.load(f)
            else:
                self.notes:dict[int, str] = {}
        except Exception as e:
            raise e
        
        self.page_labels = [i.get_label() for i in self.document]

    def get_page_image(self, index:str|int, auto_crop:bool = True, size:QSize|None = None) -> QPixmap | None:
        page = self.get_page(index)
        if page is None:
            return None
        return self.page_to_image(page, auto_crop, size)
        
    
    def get_page(self, index:str|int) -> fitz.Page | None:
        if index is int:
            try:
                return self.document[index]
            except IndexError:
                return None
        elif index is str:
            try:
                idx = self.page_labels.index(index)
            except ValueError:
                return None
            else:
                return self.document[idx]
    
    def get_note(self, index:str|int) -> str | None:
        if index is int:
            try:
                return self.notes[index]
            except IndexError:
                return None
        elif index is str:
            try:
                idx = self.page_labels.index(index)
            except ValueError:
                return None
            else:
                return self.notes[idx]
    
    def save_note(self, index:str|int, note:str) -> None:
        if index is int:
            try:
                self.notes[index] = note
            except IndexError:
                pass
        elif index is str:
            try:
                idx = self.page_labels.index(index)
            except ValueError:
                return
            else:
                self.notes[idx] = note
    
    def save_note_to_file(self) -> None:
        try:
            with open(self.note_path, "w") as f:
                json.dump(self.notes, f)
        except Exception as e:
            raise e
    
    def search_page(self, keyword:str) -> list[fitz.Page]:
        pages:list[fitz.Page] = []
        for i,label in enumerate(self.page_labels):
            if keyword in label.lower():
                pages.append(self.document[i])
        return pages
    
    @classmethod
    def page_to_image(cls, page:fitz.Page, auto_crop:bool = True ,size:QSize|None = None) -> QPixmap | None:
        pix = page.get_pixmap()
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        if auto_crop and pix.width > pix.height * CROP_THRESHOLD:
            qimage = qimage.copy(QRect(0, 0, qimage.width() // 2, qimage.height()))

        if size is None:
            qpixmap = QPixmap.fromImage(qimage)
        else:
            qpixmap = QPixmap.fromImage(qimage.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        return qpixmap
        