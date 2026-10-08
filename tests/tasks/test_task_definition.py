from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel

from eos import Context, Device, File, Param, Resource, task
from eos.tasks.exceptions import EosTaskExecutionError

CONTEXT = Context(task_name="task_name", protocol_run_name="run_name")


class FakeFileDb:
    """Minimal stand-in for FileDbInterface that records uploads in memory."""

    def __init__(self, files: dict[str, bytes] | None = None):
        self.stored: dict[str, bytes | Path] = {}
        self._preloaded = files or {}

    async def store_file(self, key: str, data: bytes | Path) -> None:
        self.stored[key] = data

    async def get_file(self, key: str) -> bytes:
        return self._preloaded[key]


class Beaker(Resource, type="beaker"): ...


class Mixer(Device, type="mixer"): ...


class Outputs(BaseModel):
    out_param: str = Param(desc="Echoed parameter")
    volume: float = Param(unit="mL")
    report: bytes = Param(file_name="report.bin")
    debug: bytes | None = None


@task("Mix")
async def mix(
    mixer: Mixer,
    beaker: Beaker,
    spare: Beaker | None = None,
    param1: str = Param(desc="A parameter"),
    speed: int = Param(10, unit="rpm", min=1, max=100, group="Motion"),
    mode: Literal["fast", "slow"] = "fast",
    spot: tuple[int, int] = (0, 0),
    calibration: File | None = None,
) -> Outputs:
    """Mix a beaker."""
    beaker.meta["mixed"] = True
    return Outputs(out_param=param1, volume=1.5, report=b"content")


@pytest.fixture
def beaker():
    return Resource(name="b1", type="beaker", meta={"location": "shelf"})


class TestTaskSpec:
    def test_spec_from_signature(self):
        spec = mix.spec
        assert spec.type == "Mix"
        assert spec.desc == "Mix a beaker."
        assert spec.devices["mixer"].type == "mixer"
        assert spec.input_resources["beaker"].type == "beaker"
        assert spec.input_resources["spare"].optional
        assert spec.input_files["calibration"].optional

    def test_parameter_specs(self):
        spec = mix.spec
        assert spec.get_parameter("param1").value is None
        assert spec.get_parameter("param1").desc == "A parameter"
        speed = spec.get_parameter("speed")
        assert (speed.type, speed.value, speed.unit, speed.min, speed.max) == ("int", 10, "rpm", 1, 100)
        assert "speed" in spec.input_parameters["Motion"].params
        assert spec.get_parameter("mode").choices == ["fast", "slow"]
        spot = spec.get_parameter("spot")
        assert (spot.type, spot.element_type, spot.length, spot.value) == ("list", "int", 2, [0, 0])

    def test_output_specs(self):
        spec = mix.spec
        assert spec.output_parameters["volume"].unit == "mL"
        assert set(spec.output_files) == {"report.bin", "debug"}
        assert set(spec.output_resources) == {"beaker", "spare"}

    def test_requires_async_function(self):
        with pytest.raises(TypeError, match="async"):

            @task("Sync")
            def sync_task() -> None:
                pass

    def test_requires_annotations(self):
        with pytest.raises(TypeError, match="type annotation"):

            @task("Untyped")
            async def untyped(value) -> None:
                pass

    def test_rejects_optional_parameters(self):
        with pytest.raises(TypeError, match="cannot be optional"):

            @task("Optional Param")
            async def optional_param(value: int | None = None) -> None:
                pass

    def test_rejects_unsupported_parameter_types(self):
        with pytest.raises(TypeError, match="unsupported type"):

            @task("Bad Type")
            async def bad_type(value: set[int]) -> None:
                pass

    def test_rejects_devices_without_type(self):
        class Untyped(Device): ...

        with pytest.raises(TypeError, match="declares no type"):

            @task("Untyped Device")
            async def untyped_device(device: Untyped) -> None:
                pass

    def test_rejects_invalid_defaults(self):
        with pytest.raises(TypeError, match="invalid spec"):

            @task("Out Of Bounds")
            async def out_of_bounds(value: int = Param(200, max=100)) -> None:
                pass

    def test_rejects_group_and_parameter_name_clash(self):
        with pytest.raises(TypeError, match="conflicts with a parameter group"):

            @task("Group Clash")
            async def group_clash(rate: int = Param(1, group="speed"), speed: int = 2) -> None:
                pass

    def test_rejects_duplicate_output_file_names(self):
        class Outputs(BaseModel):
            a: bytes = Param(file_name="data.csv")
            b: bytes = Param(file_name="data.csv")

        with pytest.raises(TypeError, match="reuses output file name"):

            @task("Duplicate Files")
            async def duplicate_files() -> Outputs:
                pass

    def test_promotes_int_defaults_for_floats(self):
        @task("Int Defaults")
        async def int_defaults(
            rate: float = 1, gains: tuple[float, float] = Param((1, 2), min=(0, 0), max=(5, 5))
        ) -> None:
            pass

        assert int_defaults.spec.get_parameter("rate").value == 1.0
        gains = int_defaults.spec.get_parameter("gains")
        assert (gains.value, gains.min, gains.max) == ([1.0, 2.0], [0.0, 0.0], [5.0, 5.0])

    def test_resource_types_cannot_declare_fields(self):
        with pytest.raises(TypeError, match="cannot declare fields"):

            class Flask(Resource, type="flask"):
                volume: float = 0

    def test_subclasses_inherit_types(self):
        class SmallBeaker(Beaker): ...

        class FastMixer(Mixer): ...

        assert (SmallBeaker.resource_type, FastMixer.device_type) == ("beaker", "mixer")


class TestTaskExecution:
    @pytest.mark.asyncio
    async def test_execute_uploads_files_and_returns_outputs(self, beaker):
        fake_db = FakeFileDb()

        parameters, resources, file_names = await mix.execute(
            CONTEXT, {"mixer": object()}, {"param1": "value1"}, {"beaker": beaker}, {}, lambda: fake_db
        )

        assert parameters == {"out_param": "value1", "volume": 1.5}
        assert resources["beaker"].meta == {"location": "shelf", "mixed": True}
        assert type(resources["beaker"]) is Resource
        assert file_names == ["report.bin"]
        assert fake_db.stored == {"run_name/task_name/report.bin": b"content"}

    @pytest.mark.asyncio
    async def test_inputs_receive_defaults_and_declared_types(self, beaker):
        received = {}

        @task("Inspect")
        async def inspect_inputs(
            ctx: Context,
            beaker: Beaker,
            spare: Beaker | None = None,
            speed: int = Param(10),
            spot: tuple[int, int] = (0, 0),
        ) -> None:
            received.update(ctx=ctx, beaker=beaker, spare=spare, speed=speed, spot=spot)

        await inspect_inputs.execute(CONTEXT, {}, {"spot": [1, 2]}, {"beaker": beaker}, {})

        assert received["ctx"] == CONTEXT
        assert isinstance(received["beaker"], Beaker)
        assert received["spare"] is None
        assert received["speed"] == 10
        assert received["spot"] == (1, 2)

    @pytest.mark.asyncio
    async def test_returned_resources_replace_inputs(self, beaker):
        class MoveOutputs(BaseModel):
            beaker: Beaker

        @task("Move")
        async def move(beaker: Beaker) -> MoveOutputs:
            return MoveOutputs(beaker=Beaker(name=beaker.name, type="beaker", meta={"location": "bench"}))

        _, resources, _ = await move.execute(CONTEXT, {}, {}, {"beaker": beaker}, {})
        assert resources["beaker"].meta == {"location": "bench"}

    @pytest.mark.asyncio
    async def test_execute_failure(self, beaker):
        @task("Failing")
        async def failing() -> None:
            raise ValueError("Test error")

        with pytest.raises(EosTaskExecutionError, match="Test error"):
            await failing.execute(CONTEXT, {}, {}, {}, {})

    @pytest.mark.asyncio
    async def test_wrong_return_type_fails(self):
        @task("Wrong Return")
        async def wrong_return() -> Outputs:
            return {"out_param": "x"}

        with pytest.raises(EosTaskExecutionError, match="must return Outputs"):
            await wrong_return.execute(CONTEXT, {}, {}, {}, {})

    @pytest.mark.asyncio
    async def test_missing_storage_when_files_returned_fails(self, beaker):
        with pytest.raises(EosTaskExecutionError, match="No file storage"):
            await mix.execute(CONTEXT, {"mixer": object()}, {"param1": "v"}, {"beaker": beaker}, {})

    @pytest.mark.asyncio
    async def test_no_connection_opened_when_no_files(self):
        class CountOutputs(BaseModel):
            x: int

        @task("No Files")
        async def no_files() -> CountOutputs:
            return CountOutputs(x=1)

        def exploding_provider():
            raise AssertionError("provider must not be called when there are no files")

        result = await no_files.execute(CONTEXT, {}, {}, {}, {}, exploding_provider)
        assert result == ({"x": 1}, {}, [])

    @pytest.mark.asyncio
    async def test_dynamic_output_files(self):
        class DynamicOutputs(BaseModel):
            files: dict[str, bytes]

        @task("Dynamic Files")
        async def dynamic_files() -> DynamicOutputs:
            return DynamicOutputs(files={"a.txt": b"a", "b/c.txt": b"c"})

        fake_db = FakeFileDb()
        _, _, file_names = await dynamic_files.execute(CONTEXT, {}, {}, {}, {}, lambda: fake_db)

        assert dynamic_files.spec.output_files == {}
        assert sorted(file_names) == ["a.txt", "b/c.txt"]
        assert fake_db.stored["run_name/task_name/b/c.txt"] == b"c"

    @pytest.mark.asyncio
    async def test_path_outputs_are_passed_to_storage_unread(self, tmp_path):
        class PathOutputs(BaseModel):
            raw: Path = Param(file_name="raw.bin")
            extra: dict[str, Path]

        (tmp_path / "raw.bin").write_bytes(b"raw")
        (tmp_path / "x.csv").write_bytes(b"x")

        @task("Path Files")
        async def path_files() -> PathOutputs:
            return PathOutputs(raw=tmp_path / "raw.bin", extra={"x.csv": tmp_path / "x.csv"})

        fake_db = FakeFileDb()
        _, _, file_names = await path_files.execute(CONTEXT, {}, {}, {}, {}, lambda: fake_db)

        assert path_files.spec.output_files.keys() == {"raw.bin"}
        assert sorted(file_names) == ["raw.bin", "x.csv"]
        assert fake_db.stored["run_name/task_name/raw.bin"] == tmp_path / "raw.bin"
        assert fake_db.stored["run_name/task_name/x.csv"] == tmp_path / "x.csv"

    @pytest.mark.asyncio
    async def test_dynamic_files_cannot_overwrite_named_files(self):
        class MixedOutputs(BaseModel):
            report: bytes = Param(file_name="report.csv")
            files: dict[str, bytes]

        @task("Mixed Files")
        async def mixed_files() -> MixedOutputs:
            return MixedOutputs(report=b"a", files={"report.csv": b"b"})

        with pytest.raises(EosTaskExecutionError, match="duplicate output files"):
            await mixed_files.execute(CONTEXT, {}, {}, {}, {}, FakeFileDb)

    @pytest.mark.asyncio
    async def test_input_files_are_passed(self):
        class LengthOutputs(BaseModel):
            length: int

        @task("File Consumer Test")
        async def file_consumer(input: File) -> LengthOutputs:  # noqa: A002
            return LengthOutputs(length=len(await input.read()))

        fake_db = FakeFileDb(files={"run_name/gen/file.txt": b"hello"})
        files = {"input": File(lambda: fake_db, "run_name/gen/file.txt")}

        result = await file_consumer.execute(CONTEXT, {}, {}, {}, files)
        assert result == ({"length": 5}, {}, [])
