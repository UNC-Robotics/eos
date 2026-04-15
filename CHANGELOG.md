# Changelog

## 0.22.0

- Changed Bayesian optimizer random sampling to use BoFire's RandomStrategy when using constraints, which is more robust
- Improved protocol run execution view in the UI to update task details when task statuses change
- Improved campaign submission form when Beacon optimizer is used to show loading indicator while its loading default parameters
- Fixed error page in the UI to use dark theme when dark theme is enabled
- Fixed failing tasks not being marked as failed in the DB
- Added test for task failure

## 0.21.0

- Improved and fixed device management code to properly handle device loading, unloading, and reloading
- Fixed Bayesian optimizer random sampling not respecting constraints via rejection sampling
- Improved how error messages are displayed in the web UI
- Added copy button for error messages displayed in the web UI
- Added tests for device loading, unloading, and reloading
- Added tests for task reloading
- Fixed bugs

## 0.20.0

- Added **scheduling simulator** in the web UI, allowing users to simulate how protocol tasks would run, estimate parallelism and resource utilization, and more
- Added file change detection in the web UI editor page, warning users if source files on disk were changed outside the web UI before saving
- Added **resources view** in the web UI, allowing users to view the state of all resources in EOS, such as view metadata, and reset their state to default
- Fixed several bugs

## 0.19.0

> **Breaking Release:** This version renames experiments to protocols/protocol runs.
> Existing user code that references experiments will need to be updated.
> A migration script is provided in `scripts/migration/migrate_experiment_to_protocol.py`.

- Replaced experiments with protocols and protocol runs to describe more general lab workflows beyond experiments
- Refactored code to support the new naming
- Added search for parameters in web UI submission dialogs
- Optimized submission dialog layout to be more vertically compact
- Collapsed Beacon optimizer domain on submission dialogs by default
- Added delayed automatic refresh after making a submission
- Fixed dark theme font color of timestamp columns
- Updated documentation

## 0.18.0

- Improved entity cloning feature in the web UI to increment a number rather than appending `_clone` suffix
- Improved task, experiment, and campaign tables to use correct pagination
- Created Docker setup for running the web UI

Thanks @dirkzon and @yordan-ov!

## 0.17.0

This is the biggest EOS update to date, bringing a brand new web UI for EOS, a powerful new default optimizer called Beacon combining
traditional methods like Bayesian optimization with cutting-edge methods like LLMs, an MCP server for connecting AI agents
to EOS with 50 tools, and many improvements to the EOS scheduler and EOS internals.

- New **web UI** for designing protocols visually, submitting tasks/protocols/campaigns, monitoring optimization, inspecting devices, browsing files, streaming logs, and managing packages.
- New **Beacon** optimizer that combines Bayesian optimization with LLM reasoning.
- New **MCP server** allowing AI assistants like Claude to connect to EOS and interact with EOS.
- New **device and resource holds** in the scheduler to keep allocations locked between tasks so other protocols can't claim them mid-workflow.
- New **scheduling simulator** (`eos sim`) to simulate experiment scheduling offline without hardware.
- New REST API endpoints for optimizer state, log streaming, and package management.
- Error messages are now stored for failed tasks, protocols, and campaigns.
- On-demand tasks now go through the scheduler, improving efficiency and stability.
- Optimizer sampling is now async and no longer blocks the orchestrator loop.
- CP-SAT scheduler runs in a thread executor to avoid blocking the event loop.
- Campaign optimizer parameters can be overridden at submission time
- EOS now lazy-loads optimizers, reducing startup time and memory usage.
- Fixed a bug that caused Ray to consume large amounts of disk space.
- Refactored parts of the codebase.
- Improved performance in several parts of the codebase.
- Various bug fixes and stability improvements.
- Updated documentation.
- Updated dependencies.