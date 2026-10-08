import subprocess
from pathlib import Path


def main():
    docs_dir = Path("docs")
    build_dir = docs_dir / "_build"
    nojekyll_file = build_dir / ".nojekyll"

    cmd = ["sphinx-build", str(docs_dir), str(build_dir)]
    subprocess.run(cmd, check=True)

    nojekyll_file.touch(exist_ok=True)


if __name__ == "__main__":
    main()
