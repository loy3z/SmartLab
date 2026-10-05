"""Private attachment storage port and in-memory demo adapter.

The API validates attachment size, MIME type and ownership before saving or
reading. No public download URL is generated. A durable adapter can implement
the same contract using private object storage or a protected file store.
"""

from dataclasses import dataclass
from threading import RLock
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class StoredFile:
    id: str
    original_name: str
    content_type: str
    size: int
    owner_id: str
    data: bytes


class FileStorage(Protocol):
    def save(
        self, data: bytes, original_name: str, content_type: str, owner_id: str
    ) -> StoredFile: ...

    def get(self, file_id: str) -> StoredFile | None: ...
    def delete(self, file_id: str) -> None: ...


Storage = FileStorage


class MemoryFileStorage:
    """Single-process demo attachments; all content is lost on restart."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._files: dict[str, StoredFile] = {}

    def save(
        self, data: bytes, original_name: str, content_type: str, owner_id: str
    ) -> StoredFile:
        content = bytes(data)
        record = StoredFile(
            id=str(uuid4()),
            original_name=original_name,
            content_type=content_type,
            size=len(content),
            owner_id=owner_id,
            data=content,
        )
        with self._lock:
            self._files[record.id] = record
        return record

    def get(self, file_id: str) -> StoredFile | None:
        with self._lock:
            return self._files.get(file_id)

    def delete(self, file_id: str) -> None:
        with self._lock:
            self._files.pop(file_id, None)
