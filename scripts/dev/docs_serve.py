import subprocess
from pathlib import Path


def main():
    docs_dir = Path("docs")
    build_dir = docs_dir / "_build"

    cmd = [
        "sphinx-autobuild",
        str(docs_dir),
        str(build_dir),
        "-j",
        "auto",
        "--watch",
        "eos",
        "--watch",
        "docs",
        "--port",
        "8002",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
