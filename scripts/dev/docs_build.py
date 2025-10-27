import subprocess
from pathlib import Path

from scripts.dev.generate_llms_txt import generate_llms_txt


def main():
    docs_dir = Path("docs")
    build_dir = docs_dir / "_build"

    cmd = ["sphinx-build", str(docs_dir), str(build_dir)]
    subprocess.run(cmd, check=True)

    # Generate llms.txt
    llms_txt_file = build_dir / "llms.txt"
    generate_llms_txt(docs_dir, llms_txt_file)


if __name__ == "__main__":
    main()
