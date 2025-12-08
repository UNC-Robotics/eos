import subprocess
import sys


def main():
    subprocess.run(["ruff", "check", "eos", "tests", *sys.argv[1:]])


if __name__ == "__main__":
    main()
