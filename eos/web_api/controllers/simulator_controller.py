import asyncio
import json
import os
import shutil
import tempfile

import yaml
from litestar import Controller, post
from pydantic import BaseModel

from eos.orchestration.orchestrator import Orchestrator


class ProtocolRunConfigRequest(BaseModel):
    type: str
    iterations: int
    max_concurrent: int = 0


class SimRunRequest(BaseModel):
    packages: list[str]
    protocols: list[ProtocolRunConfigRequest]
    scheduler: str = "greedy"
    jitter: float = 0.0
    seed: int | None = None


def _find_eos_cli() -> str:
    """Find the eos CLI binary path (cached after first call)."""
    path = shutil.which("eos")
    if not path:
        raise RuntimeError("'eos' CLI not found on PATH")
    return path


_eos_cli_path: str | None = None


def _get_eos_cli() -> str:
    global _eos_cli_path  # noqa: PLW0603
    if _eos_cli_path is None:
        _eos_cli_path = _find_eos_cli()
    return _eos_cli_path


class SimulatorController(Controller):
    path = "/simulator"

    @post("/run")
    async def run_simulation(self, data: SimRunRequest, orchestrator: Orchestrator) -> dict:
        config_yaml = {
            "packages": data.packages,
            "protocols": [
                {"type": p.type, "iterations": p.iterations, "max_concurrent": p.max_concurrent} for p in data.protocols
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="eos_sim_", delete=False, dir=tempfile.gettempdir()
        ) as f:
            yaml.dump(config_yaml, f)
            config_path = f.name

        try:
            cmd = [
                _get_eos_cli(),
                "sim",
                config_path,
                "--user-dir",
                str(orchestrator._user_dir),
                "--scheduler",
                data.scheduler,
                "--jitter",
                str(data.jitter),
                "--json",
            ]
            if data.seed is not None:
                cmd.extend(["--seed", str(data.seed)])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() or "Simulation process failed"
                raise RuntimeError(error_msg)

            return json.loads(stdout.decode())
        finally:
            os.unlink(config_path)  # noqa: PTH108
