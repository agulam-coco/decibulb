"""Command-line interface for decibulb.

Usage:
    decibulb [--version] [--help]

Functions:
    build_parser: Build the top-level argument parser.
    main: Run the CLI.
"""

import argparse

from decibulb import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="decibulb",
        description="Turn an old mixer into a switch.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"decibulb {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the decibulb CLI.

    Args:
        argv: Arguments to parse. Defaults to sys.argv[1:] when None.
    """
    parser = build_parser()
    parser.parse_args(argv)
    # TODO: Dispatch to subcommands once they exist.
    parser.print_help()


if __name__ == "__main__":
    main()
