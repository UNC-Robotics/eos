import subprocess


def main():
    subprocess.run(["ruff", "check", "eos", "tests"])


if __name__ == "__main__":
    main()
