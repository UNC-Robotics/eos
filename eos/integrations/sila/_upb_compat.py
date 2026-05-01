"""Lets sila2 run under protobuf's upb (C++) impl instead of pure-Python.

sila2's `run_protoc` re-registers `SiLAFramework.proto` on later calls, which
upb rejects. This module aliases sila2's pre-built `_pb2` modules under the bare
names its generated code imports, keeping the protos registered exactly once.

Import this module before any sila2 import. The shim applies at import time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    import sila2 as _sila2
except ImportError:
    _sila2 = None

_BARE_NAME_MODULES = (
    "SiLAFramework_pb2",
    "SiLABinaryTransfer_pb2",
    "SiLAFramework_pb2_grpc",
    "SiLABinaryTransfer_pb2_grpc",
)

if _sila2 is not None:
    _pb2_dir = Path(_sila2.__file__).parent / "framework" / "pb2"
    _aliases: dict[str, object] = {}
    for _name in _BARE_NAME_MODULES:
        _path = _pb2_dir / f"{_name}.py"
        _spec = importlib.util.spec_from_file_location(_name, str(_path))
        if _spec is None or _spec.loader is None:
            raise RuntimeError(f"sila2 upb-compat: cannot load pre-built {_name} from {_path}")
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_name] = _module
        _spec.loader.exec_module(_module)
        _aliases[_name] = _module

    # Triggering these imports runs sila_error.py and binary_transfer_handler.py,
    # whose module-init run_protoc calls use our aliases (no re-registration).
    import sila2.framework.utils as _utils
    import sila2.framework.abc.sila_error as _se
    import sila2.framework.abc.binary_transfer_handler as _bth

    # sila2's run_protoc deletes the returned module from sys.modules after use.
    # Re-seat aliases so later dynamic feature compiles keep reusing them.
    for _n, _m in _aliases.items():
        sys.modules[_n] = _m

    _original_run_protoc = _utils.run_protoc

    def _run_protoc_stable(proto_file: str) -> tuple:
        for _an, _am in _aliases.items():
            sys.modules[_an] = _am
        try:
            return _original_run_protoc(proto_file)
        finally:
            for _an, _am in _aliases.items():
                sys.modules[_an] = _am

    _utils.run_protoc = _run_protoc_stable
    # `from ... import run_protoc` bound the original by name in these modules.
    _se.run_protoc = _run_protoc_stable
    _bth.run_protoc = _run_protoc_stable
    _utils.feature_definition_to_modules.__globals__["run_protoc"] = _run_protoc_stable
