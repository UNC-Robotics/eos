import io
import zipfile
from pathlib import Path
from collections.abc import AsyncIterable

from litestar import get, Controller
from litestar.response import Stream

from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError

# Constants
CHUNK_SIZE = 3 * 1024 * 1024  # 3MB


class FileController(Controller):
    """Controller for file-related endpoints."""

    path = "/files"

    @get("/download/{experiment_id:str}/{task_id:str}/{file_name:str}")
    async def download_file(
        self, experiment_id: str, task_id: str, file_name: str, orchestrator: Orchestrator
    ) -> Stream:
        """Download a specific task output file."""

        async def file_stream() -> AsyncIterable[bytes]:
            async for chunk in orchestrator.results.download_task_output_file(
                experiment_id, task_id, file_name, chunk_size=CHUNK_SIZE
            ):
                yield chunk

        return Stream(file_stream(), headers={"Content-Disposition": f"attachment; filename={file_name}"})

    @get("/download/{experiment_id:str}/{task_id:str}")
    async def download_zip(self, experiment_id: str, task_id: str, orchestrator: Orchestrator) -> Stream:
        """Download all task output files as a zip archive."""

        async def zip_stream() -> AsyncIterable[bytes]:
            file_list = await orchestrator.results.list_task_output_files(experiment_id, task_id)
            if not file_list:
                raise APIError(status_code=404, detail="No files found for this task")

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in file_list:
                    file_name = Path(file_path).name
                    zip_info = zipfile.ZipInfo(file_name)
                    zip_info.compress_type = zipfile.ZIP_DEFLATED

                    # Write file contents to zip
                    with zip_file.open(zip_info, mode="w") as file_in_zip:
                        async for chunk in orchestrator.results.download_task_output_file(
                            experiment_id, task_id, file_name
                        ):
                            file_in_zip.write(chunk)

                            # Yield data in chunks
                            if buffer.tell() > CHUNK_SIZE:
                                buffer.seek(0)
                                yield buffer.read(CHUNK_SIZE)
                                buffer.seek(0)
                                buffer.truncate()

            # Yield remaining data
            buffer.seek(0)
            yield buffer.getvalue()

        filename = f"{experiment_id}_{task_id}_output.zip"
        return Stream(zip_stream(), headers={"Content-Disposition": f"attachment; filename={filename}"})
