import asyncio
import zipfile
from pathlib import Path
from collections.abc import AsyncIterable
from typing import ClassVar

from litestar import get, Controller
from litestar.response import Stream

from eos.auth.authorization import require_role
from eos.auth.entities.user_role import Role
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError

# Constants
CHUNK_SIZE = 3 * 1024 * 1024  # 3MB


class FileController(Controller):
    """Controller for file-related endpoints."""

    path = "/files"
    guards: ClassVar = [require_role(Role.VIEWER)]

    @get("/download/{protocol_run_name:str}/{task_name:str}/{file_name:str}")
    async def download_file(
        self, protocol_run_name: str, task_name: str, file_name: str, orchestrator: Orchestrator
    ) -> Stream:
        """Download a specific task output file."""

        async def file_stream() -> AsyncIterable[bytes]:
            async for chunk in orchestrator.results.download_task_output_file(
                protocol_run_name, task_name, file_name, chunk_size=CHUNK_SIZE
            ):
                yield chunk

        return Stream(file_stream(), headers={"Content-Disposition": f"attachment; filename={file_name}"})

    @get("/download/{protocol_run_name:str}/{task_name:str}")
    async def download_zip(self, protocol_run_name: str, task_name: str, orchestrator: Orchestrator) -> Stream:
        """Download all task output files as a zip archive."""
        file_list = await orchestrator.results.list_task_output_files(protocol_run_name, task_name)
        if not file_list:
            raise APIError(status_code=404, detail="No files found for this task")

        async def zip_stream() -> AsyncIterable[bytes]:
            sink = _ZipSink()
            with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in file_list:
                    file_name = Path(file_path).name
                    with zip_file.open(file_name, mode="w") as file_in_zip:
                        async for chunk in orchestrator.results.download_task_output_file(
                            protocol_run_name, task_name, file_name
                        ):
                            await asyncio.to_thread(file_in_zip.write, chunk)
                            if sink.size > CHUNK_SIZE:
                                yield sink.drain()
            yield sink.drain()

        filename = f"{protocol_run_name}_{task_name}_output.zip"
        return Stream(zip_stream(), headers={"Content-Disposition": f"attachment; filename={filename}"})


class _ZipSink:
    """Unseekable write target, so ZipFile streams with data descriptors and never rewrites drained bytes."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self.size = 0

    def write(self, data: bytes) -> int:
        self._chunks.append(bytes(data))
        self.size += len(data)
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        self.size = 0
        return data
