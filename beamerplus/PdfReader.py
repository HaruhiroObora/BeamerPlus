import os.path
import json
import re
from dataclasses import dataclass, field

import pymupdf

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QImage, QPixmap

CROP_THRESHOLD = 2.5
DEFAULT_DPI = 400  # デフォルト解像度 (4Kディスプレイでも一切ボケない超高精細DPI)


def _decode_page_label(label: str) -> str:
    """PDFに埋め込まれたページラベルの生文字列（UTF-16BE/UTF-8の16進数表現等）を人間が読める文字列にデコード"""
    if not label:
        return ""
    label = label.strip()

    # 1. <HEX> パターン（例: <FEFF0031> や <E382B9...>）を置換・デコード
    def _decode_hex_match(m: re.Match) -> str:
        h = m.group(1)
        if len(h) % 2 == 0:
            try:
                b = bytes.fromhex(h)
                if b.startswith(b"\xfe\xff"):
                    return b.decode("utf-16-be").replace("\ufeff", "")
                if b.startswith(b"\xff\xfe"):
                    return b.decode("utf-16-le").replace("\ufeff", "")
                u8 = b.decode("utf-8")
                if u8.isprintable():
                    return u8
            except Exception:
                pass
        return m.group(0)

    res = re.sub(r"<([0-9a-fA-F]+)>", _decode_hex_match, label)
    if res != label:
        return res.strip()

    # 2. 全体が FEFF... / FFFE... などの生16進数文字列（例: "FEFF0031"）の場合
    if len(label) >= 4 and len(label) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", label):
        try:
            b = bytes.fromhex(label)
            if b.startswith(b"\xfe\xff"):
                return b.decode("utf-16-be").replace("\ufeff", "").strip()
            if b.startswith(b"\xff\xfe"):
                return b.decode("utf-16-le").replace("\ufeff", "").strip()
            u8 = b.decode("utf-8")
            if u8.isprintable():
                return u8.strip()
        except Exception:
            pass

    return label


@dataclass
class PageGroup:
    group_index: int
    label: str
    page_indices: list[int] = field(default_factory=list)


def compute_page_groups(page_labels: list[str]) -> list[PageGroup]:
    """
    ページラベルに基づいて、隣接する同一ラベル（非空文字列）を持つページをグループ化する。
    ラベルが空文字の場合は単一ページとして扱い、離れた場所にある同名ラベルはまとめない。
    """
    groups: list[PageGroup] = []
    if not page_labels:
        return groups

    current_group_pages = [0]
    current_label = page_labels[0].strip() if page_labels[0] else ""

    for i in range(1, len(page_labels)):
        lbl = page_labels[i].strip() if page_labels[i] else ""
        if lbl and lbl == current_label:
            current_group_pages.append(i)
        else:
            groups.append(PageGroup(
                group_index=len(groups),
                label=current_label,
                page_indices=current_group_pages
            ))
            current_group_pages = [i]
            current_label = lbl

    if current_group_pages:
        groups.append(PageGroup(
            group_index=len(groups),
            label=current_label,
            page_indices=current_group_pages
        ))

    return groups


class PdfReader:
    def __init__(self, path: str):
        self.path = path
        self.note_path = path + ".json"
        try:
            self.document = pymupdf.open(self.path)
        except Exception as e:
            raise e
        
        self.page_labels = [_decode_page_label(page.get_label()) for page in self.document]
        self.page_groups = compute_page_groups(self.page_labels)
        self.page_to_group: dict[int, PageGroup] = {
            p: g for g in self.page_groups for p in g.page_indices
        }
        self.page_to_canonical: dict[int, int] = {
            p: g.page_indices[0] for g in self.page_groups for p in g.page_indices
        }
        self._compute_group_keys()

        # ノート読み込み（新形式: version=2 ヘッダ付き / 旧形式: ヘッダなし 0-based インデックス）
        self.notes: dict[str, str] = {}
        if os.path.exists(self.note_path):
            try:
                with open(self.note_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # 1. 新形式（ヘッダ: version=2）の場合: notes 辞書のキーはページラベル
                        if data.get("version") == 2 and "notes" in data and isinstance(data["notes"], dict):
                            self.notes = {str(k): str(v) for k, v in data["notes"].items()}
                        # 2. 旧形式（ヘッダなし）の場合: キーは 0-based ページインデックス
                        else:
                            for k, v in data.items():
                                try:
                                    idx = int(k)
                                    if 0 <= idx < len(self.document):
                                        label_key = self.get_page_label_key(idx)
                                        if label_key not in self.notes or not self.notes[label_key]:
                                            self.notes[label_key] = str(v)
                                except (ValueError, TypeError):
                                    pass
            except Exception:
                self.notes = {}

        self._image_cache: dict[tuple[int, int, bool], QPixmap] = {}

        # しおり（目次）の抽出: [(lvl, title, page_idx), ...]
        self.toc: list[tuple[int, str, int]] = []
        try:
            raw_toc = self.document.get_toc()
            for item in raw_toc:
                if len(item) >= 3:
                    lvl = int(item[0])
                    title = _decode_page_label(str(item[1])).strip()
                    p = int(item[2])
                    page_idx = max(0, p - 1) if p > 0 else 0
                    self.toc.append((lvl, title, page_idx))
        except Exception:
            self.toc = []

    @property
    def has_toc(self) -> bool:
        return len(self.toc) > 0

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

    def _compute_group_keys(self):
        """各グループの一意なラベルキーを計算（単一のものはlabelそのもの、重複がある場合はページ番号等で識別）"""
        self.group_keys: dict[int, str] = {}
        label_seen: dict[str, int] = {}
        for group in self.page_groups:
            lbl = group.label if group.label else str(group.page_indices[0] + 1)
            count = label_seen.get(lbl, 0) + 1
            label_seen[lbl] = count
            if count == 1:
                self.group_keys[group.group_index] = lbl
            else:
                self.group_keys[group.group_index] = f"{lbl} (p.{group.page_indices[0] + 1})"

    def get_page_label_key(self, index: int) -> str:
        """指定ページのノート保存用ラベルキーを取得"""
        group = self.page_to_group.get(index)
        if group and group.group_index in self.group_keys:
            return self.group_keys[group.group_index]
        if 0 <= index < len(self.page_labels) and self.page_labels[index]:
            return self.page_labels[index]
        return str(index + 1)

    def get_group_for_page(self, index: str | int) -> PageGroup | None:
        idx = self._resolve_index(index)
        if idx is None:
            return None
        return self.page_to_group.get(idx)

    def get_canonical_page_index(self, index: str | int) -> int | None:
        idx = self._resolve_index(index)
        if idx is None:
            return None
        return self.page_to_canonical.get(idx, idx)

    def get_note(self, index: str | int) -> str | None:
        idx = self._resolve_index(index)
        if idx is not None:
            key = self.get_page_label_key(idx)
            return self.notes.get(key, "")
        elif isinstance(index, str):
            return self.notes.get(index, "")
        return None

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
        if idx is not None:
            key = self.get_page_label_key(idx)
            self.notes[key] = note
        elif isinstance(index, str):
            self.notes[index] = note

    def save_note_to_file(self) -> None:
        try:
            payload = {
                "version": 2,
                "notes": self.notes
            }
            with open(self.note_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
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
