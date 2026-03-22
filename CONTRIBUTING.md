# Contributing to EOS

Thank you for your interest in contributing to the Experiment Orchestration System!

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- Node.js and npm (for the web UI)
- Docker and Docker Compose (for PostgreSQL and SeaweedFS)

### Getting Started

```shell
git clone https://github.com/UNC-Robotics/eos
cd eos
uv venv
source .venv/bin/activate
uv sync
```

Start the external services:

```shell
cp .env.example .env  # Edit and provide values
docker compose up -d
```

### Web UI Setup

```shell
cd web_ui
cp .env.example .env  # Edit and provide values
npm install
```

## Running EOS

```shell
eos start        # Start the orchestrator
eos ui           # Start the EOS UI (separate terminal)
eos ui --dev     # Start the EOS UI dev server
```

## Code Quality

### EOS

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```shell
eos_lint         # Check for lint issues
eos_format       # Auto-format code
```

### EOS UI

```shell
cd web_ui
npm run lint         # ESLint
npm run lint:fix     # ESLint with auto-fix
npm run format       # Prettier
```

## Testing

```shell
eos_test                    # Run all tests with coverage
eos_test -m "not slow"      # Skip slow tests
```

## Documentation

Documentation is built with Sphinx:

```shell
eos_docs_build    # Build locally
eos_docs_serve    # Serve locally
```

## Submitting Changes

1. Fork the repository and create a branch from `master`
2. Make your changes
3. Ensure `eos_lint` and `eos_test` pass
4. Submit a pull request against `master`

## License

By contributing, you agree that your contributions will be licensed under the BSD 3-Clause License.