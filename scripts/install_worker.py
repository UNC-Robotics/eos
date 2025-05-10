#!/usr/bin/env python3
"""
Install script for EOS worker dependencies
"""

import subprocess
import sys
import argparse


def run(cmd):
    """Run a shell command and exit on failure."""
    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install EOS worker dependencies")
    parser.add_argument("--optimizer", action="store_true", help="Also install optimizer_worker dependencies")
    args = parser.parse_args()

    # Install EOS CLI stub
    run(["uv", "pip", "install", "-e", ".", "--no-deps"])

    # Install worker dependencies
    run(["uv", "sync", "--only-group", "worker", "--inexact"])

    # Optionally install optimizer_worker dependencies
    if args.optimizer:
        run(["uv", "sync", "--only-group", "optimizer_worker", "--inexact"])
