import subprocess


def main():
    subprocess.run(["ruff", "format", "eos", "tests", "docker"], check=True)


if __name__ == "__main__":
    main()
