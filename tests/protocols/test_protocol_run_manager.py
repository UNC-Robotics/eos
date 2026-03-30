from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRunSubmission
from eos.protocols.exceptions import EosProtocolRunStateError
from tests.fixtures import *

PROTOCOL = "water_purification"


@pytest.mark.parametrize("setup_lab_protocol", [("small_lab", PROTOCOL)], indirect=True)
class TestProtocolRunManager:
    @pytest.mark.asyncio
    async def test_create_protocol_run(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run_2", owner="test")
        )

        protocol_run1 = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run1.name == "test_protocol_run"
        protocol_run2 = await protocol_run_manager.get_protocol_run(db, "test_protocol_run_2")
        assert protocol_run2.name == "test_protocol_run_2"

    @pytest.mark.asyncio
    async def test_create_protocol_run_nonexistent_type(self, db, protocol_run_manager):
        with pytest.raises(EosProtocolRunStateError):
            await protocol_run_manager.create_protocol_run(
                db, ProtocolRunSubmission(type="nonexistent", name="test_protocol_run", owner="test")
            )

    @pytest.mark.asyncio
    async def test_create_existing_protocol_run(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )

        with pytest.raises(EosProtocolRunStateError):
            await protocol_run_manager.create_protocol_run(
                db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
            )

    @pytest.mark.asyncio
    async def test_delete_protocol_run(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )

        protocol_run = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run.name == "test_protocol_run"

        await protocol_run_manager.delete_protocol_run(db, "test_protocol_run")

        protocol_run = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_protocol_run(self, db, protocol_run_manager):
        with pytest.raises(EosProtocolRunStateError):
            await protocol_run_manager.delete_protocol_run(db, "non_existing_protocol_run")

    @pytest.mark.asyncio
    async def test_get_protocol_runs_by_status(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run_2", owner="test")
        )
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run_3", owner="test")
        )

        await protocol_run_manager.start_protocol_run(db, "test_protocol_run")
        await protocol_run_manager.start_protocol_run(db, "test_protocol_run_2")
        await protocol_run_manager.complete_protocol_run(db, "test_protocol_run_3")

        running_protocol_runs = await protocol_run_manager.get_protocol_runs(db, status=ProtocolRunStatus.RUNNING.value)
        completed_protocol_runs = await protocol_run_manager.get_protocol_runs(
            db, status=ProtocolRunStatus.COMPLETED.value
        )

        assert running_protocol_runs == [
            await protocol_run_manager.get_protocol_run(db, "test_protocol_run"),
            await protocol_run_manager.get_protocol_run(db, "test_protocol_run_2"),
        ]

        assert completed_protocol_runs == [await protocol_run_manager.get_protocol_run(db, "test_protocol_run_3")]

    @pytest.mark.asyncio
    async def test_set_protocol_run_status(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )
        protocol_run = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run.status == ProtocolRunStatus.CREATED

        await protocol_run_manager.start_protocol_run(db, "test_protocol_run")
        protocol_run = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run.status == ProtocolRunStatus.RUNNING

        await protocol_run_manager.complete_protocol_run(db, "test_protocol_run")
        protocol_run = await protocol_run_manager.get_protocol_run(db, "test_protocol_run")
        assert protocol_run.status == ProtocolRunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_protocol_run_status_nonexistent(self, db, protocol_run_manager):
        with pytest.raises(EosProtocolRunStateError):
            await protocol_run_manager.start_protocol_run(db, "nonexistent_protocol_run")

    @pytest.mark.asyncio
    async def test_get_all_protocol_runs(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run", owner="test")
        )
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run_2", owner="test")
        )
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type=PROTOCOL, name="test_protocol_run_3", owner="test")
        )

        protocol_runs = await protocol_run_manager.get_protocol_runs(db)
        assert protocol_runs == [
            await protocol_run_manager.get_protocol_run(db, "test_protocol_run"),
            await protocol_run_manager.get_protocol_run(db, "test_protocol_run_2"),
            await protocol_run_manager.get_protocol_run(db, "test_protocol_run_3"),
        ]
