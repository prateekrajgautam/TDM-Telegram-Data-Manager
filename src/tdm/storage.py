"""Storage backends: write downloaded/exported files to local paths or a
remote server over SFTP, so TDM can save directly to local or remote
directories without an intermediate copy step.
"""
from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

from app.logger import get_logger

log = get_logger("storage")


class StorageBackend(ABC):
    """A destination TDM can stream downloaded bytes into."""

    @abstractmethod
    def open_write(self, relative_path: str):
        """Return a binary, writable, seekable-if-possible file-like object."""

    @abstractmethod
    def open_read(self, relative_path: str):
        """Return a binary, readable file-like object."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        ...

    @abstractmethod
    def size(self, relative_path: str) -> int:
        ...

    @abstractmethod
    def resolved_path(self, relative_path: str) -> str:
        ...

    def close(self) -> None:
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _full(self, relative_path: str) -> str:
        full = os.path.normpath(os.path.join(self.base_dir, relative_path))
        if not full.startswith(os.path.normpath(self.base_dir)):
            raise ValueError("Path escapes storage base directory")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    def open_write(self, relative_path: str):
        return open(self._full(relative_path), "wb")

    def open_read(self, relative_path: str):
        return open(self._full(relative_path), "rb")

    def exists(self, relative_path: str) -> bool:
        return os.path.exists(self._full(relative_path))

    def size(self, relative_path: str) -> int:
        return os.path.getsize(self._full(relative_path))

    def resolved_path(self, relative_path: str) -> str:
        return self._full(relative_path)


class SFTPStorageBackend(StorageBackend):
    """Streams files directly to a remote server over SFTP — no local
    intermediate copy is made. Configure host/port/username and either
    password or a private key.
    """

    def __init__(self, host: str, port: int, username: str, base_path: str,
                 password: str | None = None, private_key: str | None = None):
        import paramiko

        self.base_path = PurePosixPath(base_path)
        self._transport = paramiko.Transport((host, port))
        if private_key:
            key = paramiko.RSAKey.from_private_key(io.StringIO(private_key))
            self._transport.connect(username=username, pkey=key)
        else:
            self._transport.connect(username=username, password=password)
        self.sftp = paramiko.SFTPClient.from_transport(self._transport)
        self._mkdirs(str(self.base_path))

    def _mkdirs(self, remote_dir: str) -> None:
        parts = PurePosixPath(remote_dir).parts
        cur = ""
        for part in parts:
            cur = f"{cur}/{part}".replace("//", "/") if cur else part
            try:
                self.sftp.stat(cur)
            except IOError:
                try:
                    self.sftp.mkdir(cur)
                except IOError:
                    pass

    def _full(self, relative_path: str) -> str:
        full = str(self.base_path / relative_path)
        self._mkdirs(os.path.dirname(full))
        return full

    def open_write(self, relative_path: str):
        return self.sftp.open(self._full(relative_path), "wb")

    def open_read(self, relative_path: str):
        return self.sftp.open(self._full(relative_path), "rb")

    def exists(self, relative_path: str) -> bool:
        try:
            self.sftp.stat(self._full(relative_path))
            return True
        except IOError:
            return False

    def size(self, relative_path: str) -> int:
        return self.sftp.stat(self._full(relative_path)).st_size

    def resolved_path(self, relative_path: str) -> str:
        return f"sftp://{self._full(relative_path)}"

    def close(self) -> None:
        try:
            self.sftp.close()
            self._transport.close()
        except Exception:
            pass


def build_backend(storage_type: str, config: dict) -> StorageBackend:
    if storage_type == "local":
        return LocalStorageBackend(base_dir=config["base_dir"])
    if storage_type == "sftp":
        return SFTPStorageBackend(
            host=config["host"],
            port=int(config.get("port", 22)),
            username=config["username"],
            base_path=config.get("base_path", "."),
            password=config.get("password"),
            private_key=config.get("private_key"),
        )
    raise ValueError(f"Unknown storage backend type: {storage_type}")
