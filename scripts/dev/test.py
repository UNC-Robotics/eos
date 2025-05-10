import subprocess
import sys


def main():
    cmd = ["pytest"] + sys.argv[1:]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
