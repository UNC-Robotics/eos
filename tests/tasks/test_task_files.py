from eos.database.file_db_interface import FileDbInterface, get_worker_file_db
from eos.tasks.input_file_handle import InputFileHandle
from tests.fixtures import *


class TestFileDbInterface:
    async def test_store_and_get_round_trip(self, file_db_interface):
        key = "test_io/round_trip.bin"
        await file_db_interface.store_file(key, b"hello world")
        assert await file_db_interface.get_file(key) == b"hello world"
        await file_db_interface.delete_file(key)

    async def test_stream_reassembles_original(self, file_db_interface):
        key = "test_io/stream.bin"
        data = b"0123456789" * 1000
        await file_db_interface.store_file(key, data)
        out = b""
        async for chunk in file_db_interface.stream_file(key, chunk_size=1024):
            out += chunk
        assert out == data
        await file_db_interface.delete_file(key)

    async def test_list_files_by_prefix(self, file_db_interface):
        await file_db_interface.store_file("test_list/a.txt", b"a")
        await file_db_interface.store_file("test_list/b.txt", b"b")
        listed = await file_db_interface.list_files("test_list/")
        assert set(listed) >= {"test_list/a.txt", "test_list/b.txt"}
        await file_db_interface.delete_file("test_list/a.txt")
        await file_db_interface.delete_file("test_list/b.txt")

    def test_get_worker_file_db_caches_and_skips_bucket_check(self, eos_config):
        first = get_worker_file_db(eos_config.file_db)
        second = get_worker_file_db(eos_config.file_db)
        assert first is second
        assert isinstance(first, FileDbInterface)


class TestInputFileHandle:
    async def test_read(self, file_db_interface):
        key = "test_handle/read.bin"
        await file_db_interface.store_file(key, b"payload")
        handle = InputFileHandle(lambda: file_db_interface, key)
        assert await handle.read() == b"payload"
        await file_db_interface.delete_file(key)

    async def test_stream(self, file_db_interface):
        key = "test_handle/stream.bin"
        data = b"x" * 5000
        await file_db_interface.store_file(key, data)
        handle = InputFileHandle(lambda: file_db_interface, key)
        out = b""
        async for chunk in handle.stream(chunk_size=512):
            out += chunk
        assert out == data
        await file_db_interface.delete_file(key)

    async def test_download_to(self, file_db_interface, tmp_path):
        key = "test_handle/download.bin"
        await file_db_interface.store_file(key, b"to disk")
        handle = InputFileHandle(lambda: file_db_interface, key)
        dest = tmp_path / "out.bin"
        await handle.download_to(dest)
        assert dest.read_bytes() == b"to disk"
        await file_db_interface.delete_file(key)
