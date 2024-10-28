import io
from collections.abc import AsyncIterable

from minio import Minio, S3Error

from eos.configuration.entities.eos_config import DbConfig
from eos.logging.logger import log
from eos.persistence.exceptions import EosFileDbError


class FileDbInterface:
    """
    Provides access to a MinIO server for storing and retrieving files.
    """

    def __init__(self, file_db_credentials: DbConfig, bucket_name: str = "eos"):
        endpoint = f"{file_db_credentials.host}:{file_db_credentials.port}"

        self._client = Minio(
            endpoint,
            access_key=file_db_credentials.username,
            secret_key=file_db_credentials.password,
            secure=False,
        )
        self._bucket_name = bucket_name

        if not self._client.bucket_exists(self._bucket_name):
            self._client.make_bucket(self._bucket_name)

        log.debug("File database manager initialized.")

    def store_file(self, path: str, file_data: bytes) -> None:
        """
        Store a file at the specified path.
        """
        try:
            self._client.put_object(self._bucket_name, path, io.BytesIO(file_data), len(file_data))
            log.debug(f"File at path '{path}' uploaded successfully.")
        except S3Error as e:
            raise EosFileDbError(f"Error uploading file at path '{path}': {e!s}") from e

    def delete_file(self, path: str) -> None:
        """
        Delete a file at the specified path.
        """
        try:
            self._client.remove_object(self._bucket_name, path)
            log.debug(f"File at path '{path}' deleted successfully.")
        except S3Error as e:
            raise EosFileDbError(f"Error deleting file at path '{path}': {e!s}") from e

    def get_file(self, path: str) -> bytes:
        """
        Retrieve an entire file at the specified path.
        """
        response = None
        try:
            response = self._client.get_object(self._bucket_name, path)
            return response.read()
        except S3Error as e:
            raise EosFileDbError(f"Error retrieving file at path '{path}': {e!s}") from e
        finally:
            if response:
                response.close()
                response.release_conn()

    async def stream_file(self, path: str, chunk_size: int = 3 * 1024 * 1024) -> AsyncIterable[bytes]:
        """
        Stream a file at the specified path. More memory efficient than get_file.
        """
        response = None
        try:
            response = self._client.get_object(self._bucket_name, path)
            while True:
                data = response.read(chunk_size)
                if not data:
                    break
                yield data
        except S3Error as e:
            raise EosFileDbError(f"Error streaming file at path '{path}': {e!s}") from e
        finally:
            if response:
                response.close()
                response.release_conn()

    def list_files(self, prefix: str = "") -> list[str]:
        """
        List files with the specified prefix.
        """
        objects = self._client.list_objects(self._bucket_name, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
