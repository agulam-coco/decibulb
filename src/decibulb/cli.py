"""Command-line interface for decibulb.

Usage:
    decibulb [--version] [--help]
    decibulb monitor [--profile NAME] [--port PORT] [--raw]

Functions:
    build_parser: Build the top-level argument parser.
    format_event: Render a ControlEvent as one line of text.
    cmd_monitor: Print live events from a board.
    main: Run the CLI.
"""

import argparse
import sys

from decibulb import __version__
from decibulb.boards.mackie import MackieBoard
from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import load_profile

DEFAULT_PROFILE = "zoom-r24"
BAR_WIDTH = 20
NAME_WIDTH = 10


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

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    monitor = commands.add_parser("monitor", help="show live events from a board")
    monitor.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"board profile to use (default: {DEFAULT_PROFILE})",
    )
    monitor.add_argument("--port", help="exact MIDI port name (default: auto-detect)")
    monitor.add_argument("--raw", action="store_true", help="also show raw MIDI messages")
    monitor.set_defaults(func=cmd_monitor)

    return parser


def format_event(event: ControlEvent) -> str:
    """Render a ControlEvent as one line of text.

    Args:
        event: The event to render.

    Returns:
        A line such as "fader.1    ████████░░░░  0.62".
    """
    name = f"{event.control:<{NAME_WIDTH}}"
    if event.kind is ControlKind.FADER:
        filled = round(event.value * BAR_WIDTH)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        return f"{name} {bar} {event.value:.2f}"
    if event.kind is ControlKind.ENCODER:
        arrow = "→" if event.value > 0 else "←"
        return f"{name} {arrow} {event.value:+.0f}"
    return f"{name} {'pressed' if event.pressed else 'released'}"


def cmd_monitor(args: argparse.Namespace) -> int:
    """Print live events from a board until interrupted.

    Args:
        args: Parsed arguments with `profile`, `port`, and `raw`.

    Returns:
        Exit code.

    Raises:
        OSError: If the board's MIDI port can't be found.
    """
    profile = load_profile(args.profile)
    board = MackieBoard(profile, args.port)
    print(f"Listening to {profile.name} on {board.port_name}. Press Ctrl+C to stop.")

    try:
        for msg, event in board.read():
            if event is None:
                print(f"{'skipped':<{NAME_WIDTH}} {msg}")
            elif args.raw:
                print(f"{format_event(event):<45} {msg}")
            else:
                print(format_event(event))
    except KeyboardInterrupt:
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the decibulb CLI.

    Args:
        argv: Arguments to parse. Defaults to sys.argv[1:] when None.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except OSError as err:
        print(f"decibulb: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())