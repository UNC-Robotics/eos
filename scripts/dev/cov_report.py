import subprocess


def main():
    subprocess.run(["coverage", "html"], check=True)


if __name__ == "__main__":
    main()
