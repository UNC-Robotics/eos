# Changelog

## 0.18.0

- Improved entity cloning feature in the web UI to increment a number rather than appending `_clone` suffix
- Improved task, experiment, and campaign tables to use correct pagination
- Created Docker setup for running the web UI

Thanks @dirkzon and @yordan-ov!

## 0.17.0

This is the biggest EOS update to date, bringing a brand new web UI for EOS, a powerful new default optimizer called Beacon combining
traditional methods like Bayesian optimization with cutting-edge methods like LLMs, an MCP server for connecting AI agents
to EOS with 50 tools, and many improvements to the EOS scheduler and EOS internals.

- New **web UI** for designing experiments visually, submitting tasks/experiments/campaigns, monitoring optimization, inspecting devices, browsing files, streaming logs, and managing packages.
- New **Beacon** optimizer that combines Bayesian optimization with LLM reasoning.
- New **MCP server** allowing AI assistants like Claude to connect to EOS and interact with EOS.
- New **device and resource holds** in the scheduler to keep allocations locked between tasks so other experiments can't claim them mid-workflow.
- New **scheduling simulator** (`eos sim`) to simulate experiment scheduling offline without hardware.
- New REST API endpoints for optimizer state, log streaming, and package management.
- Error messages are now stored for failed tasks, experiments, and campaigns.
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