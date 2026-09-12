<p align="center">
    <img src="docs/_static/img/eos-logo.png" alt="EOS logo" width="400">
</p>

<h1 align="center">The Experiment Orchestration System (EOS)</h1>
<h3 align="center">Foundation for laboratory automation</h3>

![python](https://img.shields.io/badge/Python-3.11+-darkgreen)
[![Docs](https://img.shields.io/badge/Docs-Available-brightgreen)](https://unc-robotics.github.io/eos/)
![license](https://img.shields.io/badge/License-BSD_3--Clause-blue)

EOS is a software framework and runtime for laboratory automation, designed to serve as
the foundation for one or more automated or self-driving labs (SDLs).

**Core**

* Plugin system for defining labs, devices, tasks, protocols, and optimizers
* Package system for sharing and reusing automation code
* Validation of protocols, parameters, and configurations at load time and runtime

**Execution & Scheduling**

* Central orchestrator that coordinates devices and protocols across multiple computers
* Intelligent task scheduling with dynamic device and resource allocation
* Scheduling simulation for testing strategies offline without hardware

**Optimization**

* Built-in Bayesian optimization for protocol run campaigns, with single and multi-objective support
* Beacon optimizer that combines a [pluggable algorithm](https://unc-robotics.github.io/eos/user-guide/custom_beacon.html) with AI reasoning

**Interfaces**

* Web UI with visual protocol editor, real-time monitoring, device inspector, and file browser
* REST API with OpenAPI documentation
* MCP server for connecting AI assistants
* Optional authentication with role-based access and personal API tokens
* SiLA 2 instrument protocol integration

Documentation is available at [https://unc-robotics.github.io/eos/](https://unc-robotics.github.io/eos/).

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js and npm, and Docker Compose.
Then clone EOS and run the setup wizard:

```shell
git clone https://github.com/UNC-Robotics/eos
cd eos
uv sync --all-groups
source .venv/bin/activate
eos setup
eos services up
eos start
```

In another terminal, install and start the web UI:

```shell
cd eos/web_ui
source ../.venv/bin/activate
npm install
eos start ui
```

See the [installation guide](https://unc-robotics.github.io/eos/user-guide/installation.html)
for manual configuration and platform details. The
[authentication guide](https://unc-robotics.github.io/eos/user-guide/authentication.html)
covers shared identity services and roles.

## Citation

If you use EOS for your work, please cite:

```bibtex
@inproceedings{Angelopoulos2025_EOS,
  title = {The Experiment Orchestration System ({EOS}): Comprehensive Foundation for Laboratory Automation},
  booktitle = {2025 IEEE International Conference on Robotics and Automation (ICRA)},
  author = {Angelopoulos, Angelos and Baykal, Cem and Kandel, Jade and Verber, Matthew and Cahoon, James F. and Alterovitz, Ron},
  year = {2025},
  month = may,
  pages = {15900--15906},
  doi = {10.1109/ICRA55743.2025.11128578},
}
```
