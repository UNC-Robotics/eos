<p align="center">
    <img src="docs/_static/img/eos-logo.png" alt="Alt Text" width="400">
</p>

<h1 align="center">The Experiment Orchestration System (EOS)</h1>
<h3 align="center">Foundation for laboratory automation</h3>

![python](https://img.shields.io/badge/Python-3.11+-darkgreen)
[![Docs](https://img.shields.io/badge/Docs-Available-brightgreen)](https://unc-robotics.github.io/eos/) 
![license](https://img.shields.io/badge/License-BSD_3--Clause-blue)

EOS is a comprehensive software framework and runtime for laboratory automation, designed to serve as 
the foundation for one or more automated or self-driving labs (SDLs).

EOS provides:

* A common framework to implement laboratory automation
* A plugin system for defining labs, devices, experiments, tasks, and optimizers
* A package system for sharing and reusing code and resources across the community
* Extensive static and dynamic validation of experiments, task parameters, and more
* A runtime for executing tasks, experiments, and experiment campaigns
* A central authoritative orchestrator that can communicate with and control multiple devices
* Distributed task execution and optimization using the Ray framework
* Built-in Bayesian experiment parameter optimization
* Optimized task scheduling
* Device and sample container allocation system to prevent conflicts
* Result aggregation such as automatic output file storage

Documentation is available at [https://unc-robotics.github.io/eos/](https://unc-robotics.github.io/eos/).

## Installation

EOS should be installed on a central laboratory computer that is easily accessible.

EOS requires PostgreSQL and S3-compatible object storage (SeaweedFS by default) for data and file storage. These can be 
run with Docker Compose.

1. **Install uv**
   - **Linux/Mac**
     ```shell
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - **Windows**
     ```shell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```

2. **Install EOS**
   ```shell
   git clone https://github.com/UNC-Robotics/eos
   cd eos
   uv venv
   source .venv/bin/activate
   uv sync
   ```

3. **Configure EOS**
   ```shell
   cp .env.example .env
   cp config.example.yml config.yml
   ```

   Edit both `.env` and `config.yml` and provide values for missing fields

4. **Launch External Services**
   ```shell
   docker compose up -d
   ```

5. **Start EOS**
   ```shell
   eos start

## Citation
If you use EOS for your work, please cite:
```bibtex
@inproceedings{Angelopoulos2025_EOS,
  title = {The {{Experiment Orchestration System}} ({{EOS}}): {{Comprehensive Foundation}} for {{Laboratory Automation}}},
  shorttitle = {The {{Experiment Orchestration System}} ({{EOS}})},
  booktitle = {2025 {{IEEE International Conference}} on {{Robotics}} and {{Automation}} ({{ICRA}})},
  author = {Angelopoulos, Angelos and Baykal, Cem and Kandel, Jade and Verber, Matthew and Cahoon, James F. and Alterovitz, Ron},
  year = {2025},
  month = may,
  pages = {15900--15906},
  doi = {10.1109/ICRA55743.2025.11128578},
}
```
