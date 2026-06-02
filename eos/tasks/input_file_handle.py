"""Lazy read access to a task's input file in SeaweedFS."""

import asyncio
import os
from collections.abc import AsyncIterable, Callable

from eos.database.file_db_interface import FileDbInterface


class InputFileHandle:
    """Handle to an input file. Opens the storage connection only on first read."""

    def __init__(self, file_db_provider: Callable[[], FileDbInterface], key: str):
        self._file_db_provider = file_db_provider
        self.key = key

    async def read(self) -> bytes:
        """Read the entire file into memory."""
        return await self._file_db_provider().get_file(self.key)

    def stream(self, chunk_size: int = 3 * 1024 * 1024) -> AsyncIterable[bytes]:
        """Stream the file in chunks. More memory efficient than read()."""
        return self._file_db_provider().stream_file(self.key, chunk_size)

    async def download_to(self, local_path: str | os.PathLike) -> None:
        """Stream the file to a local path without buffering it all in memory."""
        file = await asyncio.to_thread(open, local_path, "wb")
        try:
            async for chunk in self.stream():
                await asyncio.to_thread(file.write, chunk)
        finally:
            await asyncio.to_thread(file.close)
