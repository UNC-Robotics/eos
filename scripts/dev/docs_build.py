import subprocess
from pathlib import Path


def main():
    docs_dir = Path("docs")
    build_dir = docs_dir / "_build"

    cmd = ["sphinx-build", str(docs_dir), str(build_dir)]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
