"""
Run the EOS schedulers on protocol workloads and check every schedule they produce.

The production schedulers are driven through real ProtocolExecutors and managers. Task execution is simulated on a
virtual clock, where each task takes its protocol duration, so large workloads finish in seconds.
"""

import asyncio
import heapq
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from eos.allocation.allocation_manager import AllocationManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import (
    DeviceAssignmentDef,
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
)
from eos.configuration.eos_config import DatabaseType, DbConfig, SqliteDbConfig
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_device_reference, is_resource_reference
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceModel
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.resources.resource_manager import ResourceManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.cpsat_scheduler import CpSatScheduler
from eos.scheduling.greedy_scheduler import GreedyScheduler
from eos.scheduling.heuristic_scheduler import HeuristicScheduler
from eos.scheduling.utils import compute_hold_users
from eos.tasks.task_manager import TaskManager

ROOT_DIR = Path(__file__).resolve().parents[3]
BENCHMARK_USER_DIR = Path(__file__).resolve().parent / "user"
TEST_USER_DIR = ROOT_DIR / "tests" / "user"

SCHEDULERS: dict[str, type[AbstractScheduler]] = {
    "greedy": GreedyScheduler,
    "heuristic": HeuristicScheduler,
    "cpsat": CpSatScheduler,
}
STALL_TIMEOUT_S = 5.0  # Wall time with nothing running and nothing starting before a deadlock is declared


@dataclass(frozen=True)
class Scenario:
    name: str
    size: str
    user_dir: Path
    labs: tuple[str, ...]
    runs: tuple[tuple[str, int], ...]  # (protocol, count), all submitted at once


def _benchmark(name: str, size: str, *runs: tuple[str, int]) -> Scenario:
    return Scenario(name, size, BENCHMARK_USER_DIR, ("synthesis_lab",), runs)


SCENARIOS = [
    _benchmark("linear x1", "small", ("linear_synthesis", 1)),
    _benchmark("linear x4", "small", ("linear_synthesis", 4)),
    _benchmark("branched x1", "medium", ("branched_characterization", 1)),
    _benchmark("branched x4", "medium", ("branched_characterization", 4)),
    _benchmark("campaign x1", "large", ("parallel_campaign", 1)),
    _benchmark("campaign x2", "large", ("parallel_campaign", 2)),
    _benchmark("mixed", "large", ("linear_synthesis", 2), ("branched_characterization", 2), ("parallel_campaign", 1)),
    Scenario(
        "holds",
        "features",
        TEST_USER_DIR,
        ("abstract_lab",),
        (
            ("abstract_protocol", 2),
            ("abstract_protocol_2", 2),
            ("hold_test_protocol", 2),
            ("hold_test_dynamic_protocol", 2),
        ),
    ),
    Scenario(
        "hold shapes",
        "features",
        TEST_USER_DIR,
        ("abstract_lab",),
        (
            ("inherited_hold_protocol", 2),
            ("redundant_edge_hold_protocol", 2),
            ("sibling_hold_protocol", 2),
            ("parallel_hold_users_protocol", 2),
        ),
    ),
    Scenario(
        "crossing holds",
        "features",
        TEST_USER_DIR,
        ("abstract_lab",),
        (("crossing_hold_a_protocol", 1), ("crossing_hold_b_protocol", 1)),
    ),
    Scenario(
        "dynamic allocation",
        "features",
        TEST_USER_DIR,
        ("dynamic_lab",),
        (("dynamic_device_protocol", 3), ("dynamic_resource_protocol", 3)),
    ),
]


@dataclass
class Execution:
    run: str
    task: str
    start: int
    end: int | None = None
    devices: dict[str, DeviceAssignmentDef] = field(default_factory=dict)
    resources: dict[str, str] = field(default_factory=dict)


@dataclass
class Result:
    scenario: Scenario
    scheduler: str
    executions: list[Execution]
    makespan: int
    wall_s: float
    error: str | None
    violations: list[str]

    @property
    def ok(self) -> bool:
        return self.error is None and not self.violations


class VirtualTaskExecutor:
    """Stands in for the TaskExecutor: tasks take their protocol duration on a virtual clock."""

    def __init__(self, task_manager, resource_manager, scheduler, db_interface, graphs: dict[str, ProtocolGraph]):
        self._task_manager = task_manager
        self._resource_manager = resource_manager
        self._scheduler = scheduler
        self._db_interface = db_interface
        self._graphs = graphs
        self.now = 0
        self.executions: dict[tuple[str, str], Execution] = {}
        self.starts = Counter()
        self._due: list[tuple[int, int, str, str]] = []
        self._futures: dict[tuple[str, str], asyncio.Future] = {}
        self._ready: dict[tuple[str, str], asyncio.Event] = {}
        self._outputs: dict[tuple[str, str], dict] = {}

    @property
    def running(self) -> bool:
        return bool(self._due)

    async def request_task_execution(self, submission, scheduled):
        key = (submission.protocol_run_name, submission.name)
        # Bookkeeping happens before the first await, so the driver sees the start immediately
        self.starts[key] += 1
        self.executions[key] = Execution(
            *key, self.now, devices=dict(scheduled.devices), resources=dict(scheduled.resources)
        )
        duration = self._graphs[key[0]].get_task(key[1]).duration
        heapq.heappush(self._due, (self.now + duration, sum(self.starts.values()), *key))
        future = self._futures[key] = asyncio.get_running_loop().create_future()
        ready = self._ready[key] = asyncio.Event()

        async with self._db_interface.get_async_session() as db:
            # Like the TaskExecutor: resolve the resources, and return them as outputs on completion
            by_name = await self._resource_manager.get_resources_by_names(db, list(scheduled.resources.values()))
            submission.input_resources = {slot: by_name[name] for slot, name in scheduled.resources.items()}
            self._outputs[key] = submission.input_resources
            await self._task_manager.create_task(db, submission)
            await self._task_manager.start_task(db, *key)
        ready.set()
        return await future

    async def complete_next(self) -> None:
        """Advance the clock to the next completion and finish every task due then."""
        self.now = self._due[0][0]
        while self._due and self._due[0][0] == self.now:
            *_, run, task = heapq.heappop(self._due)
            await self._ready.pop((run, task)).wait()
            async with self._db_interface.get_async_session() as db:
                await self._task_manager.add_task_output(db, run, task, {}, self._outputs.pop((run, task)), [])
                await self._task_manager.complete_task(db, run, task)
                await self._scheduler.release_task(db, task, run)
            self.executions[(run, task)].end = self.now
            self._futures.pop((run, task)).set_result(None)

    def cancel_all(self) -> None:
        for future in self._futures.values():
            future.cancel()

    async def cancel_task(self, protocol_run_name, task_name):
        raise AssertionError(f"Unexpected cancellation of {protocol_run_name}.{task_name}")


def _background_work(scheduler) -> asyncio.Future | None:
    if (solve := getattr(scheduler, "_pending_solve", None)) is not None:
        return solve[0]
    return getattr(scheduler, "_pending_plan", None)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def run_scenario(
    scenario: Scenario,
    scheduler_name: str,
    scheduler_parameters: dict | None = None,
    configuration_managers: dict[Path, ConfigurationManager] | None = None,
) -> Result:
    """Run all protocol runs of a scenario to completion with one scheduler and check the schedule."""
    configuration_managers = {} if configuration_managers is None else configuration_managers
    if scenario.user_dir not in configuration_managers:
        configuration_managers[scenario.user_dir] = ConfigurationManager(user_dir=str(scenario.user_dir))
    configuration_manager = configuration_managers[scenario.user_dir]
    for lab in scenario.labs:
        if lab not in configuration_manager.labs:
            configuration_manager.load_lab(lab)
    for protocol, _ in scenario.runs:
        if protocol not in configuration_manager.protocols:
            configuration_manager.load_protocol(protocol)

    # A file database, since in-memory SQLite shares one connection and concurrent sessions would lose writes
    with tempfile.TemporaryDirectory() as db_dir:
        db_interface = SqliteDbInterface(
            DbConfig(type=DatabaseType.SQLITE, sqlite=SqliteDbConfig(db_dir=Path(db_dir), db_name="benchmark"))
        )
        await db_interface.initialize_database()
        try:
            return await _run(scenario, scheduler_name, scheduler_parameters or {}, configuration_manager, db_interface)
        finally:
            await db_interface.close()


async def _run(scenario, scheduler_name, scheduler_parameters, configuration_manager, db_interface) -> Result:
    resource_manager = ResourceManager(configuration_manager=configuration_manager)
    allocation_manager = AllocationManager(configuration_manager, db_interface)
    protocol_run_manager = ProtocolRunManager(configuration_manager)
    task_manager = TaskManager(configuration_manager, None)
    async with db_interface.get_async_session() as db:
        # Device records only: the schedulers never talk to device actors
        db.add_all(
            DeviceModel(
                name=name, lab_name=lab_name, type=device.type, computer=device.computer, meta=device.meta or {}
            )
            for lab_name, lab in configuration_manager.labs.items()
            for name, device in lab.devices.items()
        )
        await db.flush()
        await resource_manager.initialize(db)
        await allocation_manager.initialize(db)

    scheduler = SCHEDULERS[scheduler_name](
        configuration_manager,
        protocol_run_manager,
        task_manager,
        DeviceManager(configuration_manager=configuration_manager),
        allocation_manager,
    )
    if scheduler_parameters:
        await scheduler.update_parameters(scheduler_parameters)

    graphs: dict[str, ProtocolGraph] = {}
    task_executor = VirtualTaskExecutor(task_manager, resource_manager, scheduler, db_interface, graphs)
    executors: dict[str, ProtocolExecutor] = {}
    for protocol, count in scenario.runs:
        for i in range(count):
            name = f"{protocol}_{i}"
            graphs[name] = ProtocolGraph(configuration_manager.protocols[protocol])
            executors[name] = ProtocolExecutor(
                protocol_run_submission=ProtocolRunSubmission(name=name, type=protocol, owner="benchmark"),
                protocol_graph=graphs[name],
                protocol_run_manager=protocol_run_manager,
                task_manager=task_manager,
                task_executor=task_executor,
                scheduler=scheduler,
                db_interface=db_interface,
            )
            async with db_interface.get_async_session() as db:
                await executors[name].start_protocol_run(db)

    start = time.perf_counter()
    error = None
    try:
        await _drive(executors, task_executor, scheduler, db_interface)
    except Exception as e:
        chain = []
        while e is not None:
            chain.append(f"{type(e).__name__}: {e}")
            e = e.__cause__
        error = " <- ".join(chain)
    finally:
        task_executor.cancel_all()
        if isinstance(scheduler, CpSatScheduler):
            scheduler._discard_pending_solve()
    wall_s = time.perf_counter() - start

    executions = list(task_executor.executions.values())
    violations = [f"{run}.{task} started {n} times" for (run, task), n in task_executor.starts.items() if n > 1]
    violations += check_schedule(configuration_manager, graphs, executions, complete=error is None)
    return Result(
        scenario=scenario,
        scheduler=scheduler_name,
        executions=executions,
        makespan=max((e.end or 0 for e in executions), default=0),
        wall_s=wall_s,
        error=error,
        violations=violations,
    )


async def _drive(executors, task_executor: VirtualTaskExecutor, scheduler, db_interface) -> None:
    """Progress the runs until each is complete, advancing the clock whenever nothing more can start."""
    remaining = dict(executors)
    while remaining:
        stalled_since = None
        while True:
            started = sum(task_executor.starts.values())
            for name, executor in list(remaining.items()):
                async with db_interface.get_async_session() as db:
                    if await executor.progress_protocol_run(db):
                        del remaining[name]
            await _settle()
            if (pending := _background_work(scheduler)) is not None:
                await asyncio.wait({pending})
                continue
            if sum(task_executor.starts.values()) != started:
                stalled_since = None
                continue
            if task_executor.running or not remaining:
                break
            # Nothing runs and nothing starts, so only a periodic re-poll could still make progress
            stalled_since = stalled_since or time.perf_counter()
            if time.perf_counter() - stalled_since > STALL_TIMEOUT_S:
                raise RuntimeError(f"Deadlock at t={task_executor.now}: {sorted(remaining)} made no progress")
            await asyncio.sleep(0.05)
        if task_executor.running:
            await task_executor.complete_next()
            await _settle()


def check_schedule(
    configuration_manager, graphs: dict[str, ProtocolGraph], executions: list[Execution], complete: bool = True
) -> list[str]:
    """
    Check dependencies, assignments, exclusive use and holds.

    When complete, also check that every task of every run ran to completion.
    """
    by_key = {(e.run, e.task): e for e in executions}
    violations = _check_completion(graphs, by_key) if complete else []
    for e in executions:
        violations += _check_execution(configuration_manager.labs, graphs[e.run].get_task(e.task), e, by_key)
    usage = _usage(executions)
    violations += _check_exclusive_use(usage)
    violations += _check_holds(graphs, by_key, usage)
    return violations


def _check_completion(graphs: dict[str, ProtocolGraph], by_key: dict[tuple[str, str], Execution]) -> list[str]:
    violations = []
    for run, graph in graphs.items():
        missing = set(graph.get_task_graph().nodes) - {task for (r, task) in by_key if r == run}
        if missing:
            violations.append(f"{run} never ran {sorted(missing)}")
    violations += [f"{e.run}.{e.task} never completed" for e in by_key.values() if e.end is None]
    return violations


def _check_execution(labs, task, e: Execution, by_key: dict[tuple[str, str], Execution]) -> list[str]:
    where = f"{e.run}.{e.task}"
    violations = []
    for dependency in task.dependencies:
        dep = by_key.get((e.run, dependency))
        if dep is None or dep.end is None or dep.end > e.start:
            violations.append(f"{where} started at {e.start} before dependency {dependency} finished")

    if set(e.devices) != set(task.devices):
        violations.append(f"{where} got devices {sorted(e.devices)}, needs {sorted(task.devices)}")
    for slot, requirement in task.devices.items():
        if (got := e.devices.get(slot)) is not None:
            violations += [f"{where}.{slot} {v}" for v in _device_violations(labs, requirement, got, e.run, by_key)]

    if set(e.resources) != set(task.resources):
        violations.append(f"{where} got resources {sorted(e.resources)}, needs {sorted(task.resources)}")
    for slot, requirement in task.resources.items():
        if (got := e.resources.get(slot)) is not None:
            violations += [f"{where}.{slot} {v}" for v in _resource_violations(labs, requirement, got, e.run, by_key)]
    return violations


def _resource_violations(labs, requirement, got: str, run: str, by_key) -> list[str]:
    if isinstance(requirement, DynamicResourceAssignmentDef):
        types = {name: r.type for lab in labs.values() for name, r in lab.resources.items()}
        return [] if types.get(got) == requirement.resource_type else [f"got {got} of the wrong type"]
    if is_resource_reference(requirement):
        ref_task, ref_slot = requirement.split(".")
        ref = by_key.get((run, ref_task))
        return [] if ref is not None and ref.resources.get(ref_slot) == got else [f"got {got}, unlike {requirement}"]
    return [] if got == requirement else [f"got {got} instead of {requirement}"]


def _device_violations(labs, requirement, got: DeviceAssignmentDef, run: str, by_key) -> list[str]:
    pair = (got.lab_name, got.name)
    if isinstance(requirement, DeviceAssignmentDef):
        return [] if pair == (requirement.lab_name, requirement.name) else [f"got {pair}, not its specific device"]
    if isinstance(requirement, DynamicDeviceAssignmentDef):
        violations = []
        if getattr(labs[got.lab_name].devices.get(got.name), "type", None) != requirement.device_type:
            violations.append(f"got {pair} of the wrong type")
        if requirement.allowed_labs and got.lab_name not in requirement.allowed_labs:
            violations.append(f"got {pair} outside its allowed labs")
        allowed = {(d.lab_name, d.name) for d in requirement.allowed_devices or []}
        if allowed and pair not in allowed:
            violations.append(f"got {pair} outside its allowed devices")
        return violations
    ref_task, ref_slot = requirement.split(".")
    ref_device = by_key[(run, ref_task)].devices.get(ref_slot) if (run, ref_task) in by_key else None
    if ref_device is None or (ref_device.lab_name, ref_device.name) != pair:
        return [f"got {pair}, but {requirement} used {ref_device}"]
    return []


def _usage(executions: list[Execution]) -> dict[object, list[Execution]]:
    """Completed executions by the device or resource they used, in start order."""
    usage = defaultdict(list)
    for e in executions:
        if e.end is not None:
            for d in e.devices.values():
                usage[(d.lab_name, d.name)].append(e)
            for r in e.resources.values():
                usage[r].append(e)
    for uses in usage.values():
        uses.sort(key=lambda e: (e.start, e.end))
    return usage


def _check_exclusive_use(usage: dict[object, list[Execution]]) -> list[str]:
    return [
        f"{item} used by {a.run}.{a.task} and {b.run}.{b.task} at once"
        for item, uses in usage.items()
        for a, b in pairwise(uses)
        if b.start < a.end
    ]


def _check_holds(graphs, by_key, usage) -> list[str]:
    """Between a holder's start and its last hold user's end, no other run may use the held item."""
    violations = []
    for run, graph in graphs.items():
        device_users, resource_users = compute_hold_users(graph)
        for kind, holds in (("device", device_users), ("resource", resource_users)):
            for (task, slot), users in holds.items():
                holder = by_key.get((run, task))
                ends = [by_key[(run, user)].end for user in users if (run, user) in by_key]
                if holder is None or not ends or None in ends:
                    continue
                got = holder.devices.get(slot) if kind == "device" else holder.resources.get(slot)
                item = (got.lab_name, got.name) if kind == "device" else got
                window = (holder.start, max(ends))
                violations += [
                    f"{other.run}.{other.task} used {item} while {run}.{task} held it during {window}"
                    for other in usage.get(item, [])
                    if other.run != run and other.start < window[1] and other.end > window[0]
                ]
    return violations
