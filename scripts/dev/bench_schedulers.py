import subprocess
import sys


def main():
    # Runs the EOS schedulers on small, medium and large workloads, checks every schedule and reports makespans
    result = subprocess.run([sys.executable, "-m", "tests.scheduling.benchmark", *sys.argv[1:]], check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
