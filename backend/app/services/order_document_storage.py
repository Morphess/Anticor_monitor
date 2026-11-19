"""Локальне приватне файлове сховище; не монтуй його через StaticFiles."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import UploadFile

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
}


class DocumentStorageError(ValueError):
    pass


class OrderDocumentStorage:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("ORDER_DOCUMENTS_DIR", "var/order_documents")).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        # Ключ є збереженим у БД випадковим ім'ям, а не клієнтським шляхом.
        if not storage_key or Path(storage_key).name != storage_key:
            raise DocumentStorageError("Некоректний ключ сховища")
        result = (self.root / storage_key).resolve()
        if result.parent != self.root:
            raise DocumentStorageError("Некоректний шлях документа")
        return result

    def stage(self, upload: UploadFile):
        name = Path(upload.filename or "").name
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise DocumentStorageError("Підтримуються лише PDF, DOCX та ODT")
        if not name:
            raise DocumentStorageError("Вкажи ім'я файла")
        tmp_path: Path | None = None
        size = 0
        digest = hashlib.sha256()
        first_chunk = b""
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-", delete=False) as output:
                tmp_path = Path(output.name)
                while True:
                    chunk = upload.file.read(1024 * 1024)
                    if not chunk:
                        break
                    if size == 0:
                        first_chunk = chunk[:8]
                    size += len(chunk)
                    if size > MAX_DOCUMENT_BYTES:
                        raise DocumentStorageError("Документ перевищує 15 МБ")
                    output.write(chunk)
                    digest.update(chunk)
            if size == 0:
                raise DocumentStorageError("Не можна завантажити порожній документ")
            if suffix == ".pdf" and not first_chunk.startswith(b"%PDF-"):
                raise DocumentStorageError("Файл не має сигнатури PDF")
            if suffix in {".docx", ".odt"}:
                import zipfile
                if not zipfile.is_zipfile(tmp_path):
                    raise DocumentStorageError("Некоректний DOCX/ODT файл")
            return tmp_path, {
                "original_filename": name[:255],
                "content_type": ALLOWED_EXTENSIONS[suffix],
                "size_bytes": size,
                "sha256": digest.hexdigest(),
                "storage_key": f"{uuid4().hex}{suffix}",
            }
        except Exception:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            raise

    def finalize(self, staged: Path, key: str) -> Path:
        destination = self._path(key)
        os.replace(staged, destination)
        destination.chmod(0o600)
        return destination

    def verify(self, version) -> Path:
        path = self._path(version.storage_key)
        if not path.is_file():
            raise DocumentStorageError("Файл версії відсутній у сховищі")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as inp:
            for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        if digest.hexdigest() != version.sha256 or size != version.size_bytes:
            raise DocumentStorageError("Порушено цілісність версії документа (SHA-256)")
        return path
