import asyncio
from collections.abc import AsyncIterable

import boto3
from botocore.exceptions import ClientError

from eos.configuration.eos_config import FileDbConfig
from eos.database.exceptions import EosFileDbError
from eos.logging.logger import log


class FileDbInterface:
    """
    Provides access to an S3-compatible object storage for storing and retrieving files.
    """

    def __init__(self, file_db_config: FileDbConfig):
        self._client = boto3.client(
            "s3",
            endpoint_url=file_db_config.endpoint_url,
            aws_access_key_id=file_db_config.access_key_id,
            aws_secret_access_key=file_db_config.secret_access_key,
            region_name=file_db_config.region_name,
        )
        self._bucket_name = file_db_config.bucket

        try:
            self._client.head_bucket(Bucket=self._bucket_name)
        except ClientError:
            create_kwargs: dict = {"Bucket": self._bucket_name}
            if file_db_config.endpoint_url or file_db_config.region_name == "us-east-1":
                pass
            else:
                create_kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": file_db_config.region_name,
                }
            self._client.create_bucket(**create_kwargs)

        log.debug("File database interface initialized.")

    async def store_file(self, path: str, file_data: bytes) -> None:
        """
        Store a file at the specified path.
        """
        try:
            await asyncio.to_thread(self._client.put_object, Bucket=self._bucket_name, Key=path, Body=file_data)
            log.debug(f"File at path '{path}' uploaded successfully.")
        except ClientError as e:
            raise EosFileDbError(f"Error uploading file at path '{path}': {e!s}") from e

    async def delete_file(self, path: str) -> None:
        """
        Delete a file at the specified path.
        """
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket_name, Key=path)
            log.debug(f"File at path '{path}' deleted successfully.")
        except ClientError as e:
            raise EosFileDbError(f"Error deleting file at path '{path}': {e!s}") from e

    async def get_file(self, path: str) -> bytes:
        """
        Retrieve an entire file at the specified path.
        """
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket_name, Key=path)
            return await asyncio.to_thread(response["Body"].read)
        except ClientError as e:
            raise EosFileDbError(f"Error retrieving file at path '{path}': {e!s}") from e

    async def stream_file(self, path: str, chunk_size: int = 3 * 1024 * 1024) -> AsyncIterable[bytes]:
        """
        Stream a file at the specified path. More memory efficient than get_file.
        """
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket_name, Key=path)
            body = response["Body"]
            while True:
                data = await asyncio.to_thread(body.read, chunk_size)
                if not data:
                    break
                yield data
        except ClientError as e:
            raise EosFileDbError(f"Error streaming file at path '{path}': {e!s}") from e

    async def list_files(self, prefix: str = "") -> list[str]:
        """
        List files with the specified prefix.
        """

        def _list() -> list[str]:
            paginator = self._client.get_paginator("list_objects_v2")
            files = []
            for page in paginator.paginate(Bucket=self._bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    files.append(obj["Key"])
            return files

        return await asyncio.to_thread(_list)
