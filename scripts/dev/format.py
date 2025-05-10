import subprocess


def main():
    subprocess.run(["black", "."], check=True)


if __name__ == "__main__":
    main()
