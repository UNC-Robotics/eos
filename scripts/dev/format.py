import subprocess


def main():
    subprocess.run(["ruff", "format", "eos", "tests"], check=True)


if __name__ == "__main__":
    main()
