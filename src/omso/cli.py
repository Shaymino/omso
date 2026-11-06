from importlib.metadata import version


def main() -> None:
    print(f"omso {version('omso')}")
