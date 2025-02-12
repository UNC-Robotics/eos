import subprocess


def main():
    subprocess.run(["pytest", "--cov=eos"], check=True)


if __name__ == "__main__":
    main()
