import subprocess
import sys


def main():
    # Coverage slows tests by about a third, so it is opt-in: eos_test --cov
    args = ["--cov=eos" if arg == "--cov" else arg for arg in sys.argv[1:]]
    subprocess.run(["pytest", *args], check=True)


if __name__ == "__main__":
    main()
