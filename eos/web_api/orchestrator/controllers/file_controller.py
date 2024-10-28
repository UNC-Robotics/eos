import io
import zipfile
from collections.abc import AsyncIterable
from pathlib import Path

from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.response import Stream

from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.public.exception_handling import handle_exceptions

_CHUNK_SIZE = 3 * 1024 * 1024  # 3MB


class FileController(Controller):
    path = "/files"

    @get("/download/{experiment_id:str}/{task_id:str}/{file_name:str}")
    @handle_exceptions("Failed to download file")
    async def download_task_output_file(
        self, experiment_id: str, task_id: str, file_name: str, orchestrator: Orchestrator
    ) -> Stream:
        async def file_stream() -> AsyncIterable:
            try:
                async for chunk in orchestrator.results.download_task_output_file(
                    experiment_id, task_id, file_name, chunk_size=_CHUNK_SIZE
                ):
                    yield chunk
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

        return Stream(file_stream(), headers={"Content-Disposition": f"attachment; filename={file_name}"})

    @get("/download/{experiment_id:str}/{task_id:str}")
    @handle_exceptions("Failed to download zipped task output files")
    async def download_task_output_files_zipped(
        self, experiment_id: str, task_id: str, orchestrator: Orchestrator
    ) -> Stream:
        async def zip_stream() -> AsyncIterable:
            try:
                file_list = await orchestrator.results.list_task_output_files(experiment_id, task_id)

                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_path in file_list:
                        file_name = Path(file_path).name

                        zip_info = zipfile.ZipInfo(file_name)
                        zip_info.compress_type = zipfile.ZIP_DEFLATED

                        with zip_file.open(zip_info, mode="w") as file_in_zip:
                            async for chunk in orchestrator.results.download_task_output_file(
                                experiment_id, task_id, file_name
                            ):
                                file_in_zip.write(chunk)

                                if buffer.tell() > _CHUNK_SIZE:
                                    buffer.seek(0)
                                    yield buffer.read(_CHUNK_SIZE)
                                    buffer.seek(0)
                                    buffer.truncate()

                buffer.seek(0)
                while True:
                    chunk = buffer.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

        return Stream(
            zip_stream(), headers={"Content-Disposition": f"attachment; filename={experiment_id}_{task_id}_output.zip"}
        )
