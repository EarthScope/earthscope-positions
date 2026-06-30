import argparse


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="es-positions",
        description="Pull GNSS position data from the EarthScope API.",
    )
    ap.parse_args()


if __name__ == "__main__":
    main()
