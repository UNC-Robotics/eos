#!/usr/bin/env python3
"""
Migrate user code from EOS "experiment" terminology to "protocol" / "protocol run".

This script updates user packages (under a user directory) to be compatible with
EOS versions that renamed "experiment" to "protocol".

Changes applied:
  1. Renames `experiments/` directories to `protocols/`
  2. Renames `experiment.yml` files to `protocol.yml`
  3. Updates Python imports: `from eos.experiments` -> `from eos.protocols`
  4. Updates class references (ExperimentExecutor -> ProtocolExecutor, etc.)
  5. Updates variable/parameter names (experiment_type -> protocol, experiment_name -> protocol_run_name)
  6. Updates YAML content (type field values containing 'experiment' in the name)

Usage:
  python scripts/migration/migrate_experiment_to_protocol.py /path/to/user/dir
  python scripts/migration/migrate_experiment_to_protocol.py /path/to/user/dir --apply

By default runs in dry-run mode. Pass --apply to execute changes.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# --- Import path replacements ---
IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    ("from eos.experiments.entities.experiment", "from eos.protocols.entities.protocol_run"),
    ("from eos.experiments.experiment_executor_factory", "from eos.protocols.protocol_executor_factory"),
    ("from eos.experiments.experiment_executor", "from eos.protocols.protocol_executor"),
    ("from eos.experiments.experiment_manager", "from eos.protocols.protocol_run_manager"),
    ("from eos.experiments.exceptions", "from eos.protocols.exceptions"),
    ("from eos.experiments", "from eos.protocols"),
    ("from eos.configuration.entities.experiment_def", "from eos.configuration.entities.protocol_def"),
    ("from eos.configuration.experiment_graph", "from eos.configuration.protocol_graph"),
    ("from eos.orchestration.services.experiment_service", "from eos.orchestration.services.protocol_service"),
    ("from eos.web_api.controllers.experiment_controller", "from eos.web_api.controllers.protocol_controller"),
]

# --- Class/type name replacements ---
CLASS_REPLACEMENTS: list[tuple[str, str]] = [
    # Entity classes
    ("ExperimentStatus", "ProtocolRunStatus"),
    ("ExperimentSubmission", "ProtocolRunSubmission"),
    ("ExperimentModel", "ProtocolRunModel"),
    ("Experiment", "ProtocolRun"),  # Must come after ExperimentStatus/Submission/Model
    # Executor/Manager/Factory
    ("ExperimentExecutorFactory", "ProtocolExecutorFactory"),
    ("ExperimentExecutor", "ProtocolExecutor"),
    ("ExperimentManager", "ProtocolRunManager"),
    # Configuration
    ("ExperimentDef", "ProtocolDef"),
    ("ExperimentResourceDef", "ProtocolResourceDef"),
    ("ExperimentGraph", "ProtocolGraph"),
    ("ExperimentGraphBuilder", "ProtocolGraphBuilder"),
    ("ExperimentValidator", "ProtocolValidator"),
    ("ExperimentResourceRegistry", "ProtocolResourceRegistry"),
    # Service/Controller
    ("ExperimentService", "ProtocolService"),
    ("ExperimentController", "ProtocolController"),
    # Exceptions
    ("EosExperimentExecutionError", "EosProtocolRunExecutionError"),
    ("EosExperimentStateError", "EosProtocolRunStateError"),
    ("EosExperimentTaskExecutionError", "EosProtocolRunTaskExecutionError"),
    ("EosExperimentCancellationError", "EosProtocolRunCancellationError"),
    ("EosExperimentError", "EosProtocolRunError"),
    ("EosExperimentDoesNotExistError", "EosProtocolRunDoesNotExistError"),
    ("EosExperimentTypeInUseError", "EosProtocolInUseError"),
    ("EosExperimentConfigurationError", "EosProtocolConfigurationError"),
]

# --- Variable/parameter name replacements (applied as whole-word regex) ---
VARIABLE_REPLACEMENTS: list[tuple[str, str]] = [
    ("experiment_name", "protocol_run_name"),
    ("experiment_type", "protocol"),
    ("experiment_graph", "protocol_graph"),
    ("experiment_submission", "protocol_run_submission"),
    ("experiment_executor", "protocol_executor"),
    ("experiment_manager", "protocol_run_manager"),
    ("experiment_parameters", "protocol_run_parameters"),
    ("experiment_def", "protocol_def"),
]

# --- Config key replacements (in YAML files) ---
YAML_KEY_REPLACEMENTS: list[tuple[str, str]] = [
    ("experiments:", "protocols:"),
]


def find_python_files(directory: Path) -> list[Path]:
    """Find all Python files in a directory tree."""
    return sorted(directory.rglob("*.py"))


def find_yaml_files(directory: Path) -> list[Path]:
    """Find all YAML files in a directory tree."""
    yaml_files = list(directory.rglob("*.yml"))
    yaml_files.extend(directory.rglob("*.yaml"))
    return sorted(yaml_files)


def apply_text_replacements(
    content: str, replacements: list[tuple[str, str]], *, use_word_boundary: bool = False
) -> tuple[str, list[str]]:
    """Apply a list of text replacements, returning (new_content, list_of_changes)."""
    changes: list[str] = []
    for old, new in replacements:
        if use_word_boundary:
            pattern = rf"\b{re.escape(old)}\b"
            new_content = re.sub(pattern, new, content)
        else:
            new_content = content.replace(old, new)
        if new_content != content:
            count = content.count(old) if not use_word_boundary else len(re.findall(pattern, content))
            changes.append(f"  {old} -> {new} ({count} occurrence(s))")
            content = new_content
    return content, changes


def process_python_file(filepath: Path, apply: bool) -> list[str]:
    """Process a single Python file, applying all relevant replacements."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    original = content
    all_changes: list[str] = []

    # Apply import replacements (exact string match)
    content, changes = apply_text_replacements(content, IMPORT_REPLACEMENTS)
    all_changes.extend(changes)

    # Apply class name replacements (exact string match — order matters)
    content, changes = apply_text_replacements(content, CLASS_REPLACEMENTS)
    all_changes.extend(changes)

    # Apply variable name replacements (word boundary)
    content, changes = apply_text_replacements(content, VARIABLE_REPLACEMENTS, use_word_boundary=True)
    all_changes.extend(changes)

    if content != original:
        if apply:
            filepath.write_text(content, encoding="utf-8")
        return all_changes
    return []


def process_yaml_file(filepath: Path, apply: bool) -> list[str]:
    """Process a single YAML file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    original = content
    all_changes: list[str] = []

    content, changes = apply_text_replacements(content, YAML_KEY_REPLACEMENTS)
    all_changes.extend(changes)

    if content != original:
        if apply:
            filepath.write_text(content, encoding="utf-8")
        return all_changes
    return []


def rename_directories(user_dir: Path, apply: bool) -> list[str]:
    """Rename experiments/ directories to protocols/."""
    changes: list[str] = []
    # Find all 'experiments' directories (bottom-up to avoid path conflicts)
    experiment_dirs = sorted(user_dir.rglob("experiments"), reverse=True)
    for exp_dir in experiment_dirs:
        if exp_dir.is_dir():
            new_dir = exp_dir.parent / "protocols"
            if not new_dir.exists():
                changes.append(f"  {exp_dir.relative_to(user_dir)} -> {new_dir.relative_to(user_dir)}")
                if apply:
                    shutil.move(str(exp_dir), str(new_dir))
    return changes


def rename_yaml_files(user_dir: Path, apply: bool) -> list[str]:
    """Rename experiment.yml files to protocol.yml."""
    changes: list[str] = []
    for yml_file in sorted(user_dir.rglob("experiment.yml")):
        new_file = yml_file.parent / "protocol.yml"
        if not new_file.exists():
            changes.append(f"  {yml_file.relative_to(user_dir)} -> {new_file.relative_to(user_dir)}")
            if apply:
                shutil.move(str(yml_file), str(new_file))
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate EOS user code from 'experiment' to 'protocol' terminology.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("user_dir", type=Path, help="Path to the user directory to migrate")
    parser.add_argument(
        "--apply", action="store_true", help="Actually apply changes (default is dry-run)"
    )
    args = parser.parse_args()

    user_dir: Path = args.user_dir.resolve()
    apply: bool = args.apply

    if not user_dir.is_dir():
        print(f"Error: '{user_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    mode = "APPLYING" if apply else "DRY RUN"
    print(f"\n{'='*60}")
    print(f"  EOS Experiment -> Protocol Migration ({mode})")
    print(f"  User directory: {user_dir}")
    print(f"{'='*60}\n")

    total_changes = 0

    # 1. Rename directories
    print("--- Directory renames ---")
    changes = rename_directories(user_dir, apply)
    if changes:
        print("\n".join(changes))
        total_changes += len(changes)
    else:
        print("  (no directories to rename)")

    # 2. Rename YAML files
    print("\n--- YAML file renames ---")
    changes = rename_yaml_files(user_dir, apply)
    if changes:
        print("\n".join(changes))
        total_changes += len(changes)
    else:
        print("  (no YAML files to rename)")

    # 3. Process Python files
    print("\n--- Python file updates ---")
    py_files = find_python_files(user_dir)
    py_changes = 0
    for py_file in py_files:
        changes = process_python_file(py_file, apply)
        if changes:
            print(f"\n  {py_file.relative_to(user_dir)}:")
            for c in changes:
                print(f"    {c}")
            py_changes += len(changes)
    if py_changes == 0:
        print("  (no Python files to update)")
    total_changes += py_changes

    # 4. Process YAML files
    print("\n--- YAML content updates ---")
    yaml_files = find_yaml_files(user_dir)
    yaml_changes = 0
    for yaml_file in yaml_files:
        changes = process_yaml_file(yaml_file, apply)
        if changes:
            print(f"\n  {yaml_file.relative_to(user_dir)}:")
            for c in changes:
                print(f"    {c}")
            yaml_changes += len(changes)
    if yaml_changes == 0:
        print("  (no YAML content to update)")
    total_changes += yaml_changes

    # Summary
    print(f"\n{'='*60}")
    if total_changes == 0:
        print("  No changes needed! Your code is already up to date.")
    elif apply:
        print(f"  Applied {total_changes} change(s).")
    else:
        print(f"  Found {total_changes} change(s) to apply.")
        print("  Run with --apply to execute these changes.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
