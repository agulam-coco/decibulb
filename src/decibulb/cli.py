"""Command-line interface for decibulb.

Usage:
    decibulb [--version] [--help]
    decibulb monitor [--profile NAME] [--port PORT] [--raw]
    decibulb discover [--timeout SECONDS] [--blink]
    decibulb run [--config PATH] [-v | -vv]

Functions:
    build_parser: Build the top-level argument parser.
    format_event: Render a ControlEvent as one line of text.
    cmd_monitor: Print live events from a board.
    cmd_discover: List nearby lights and optionally blink each one.
    cmd_run: Control devices from a board using the config file.
    main: Run the CLI.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from decibulb import __version__, runner
from decibulb.boards.mackie import MackieBoard
from decibulb.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from decibulb.devices.govee_ble import GoveeBleBulb, discover_bulbs
from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import load_profile

DEFAULT_PROFILE = "zoom-r24"
DEFAULT_SCAN_SECONDS = 10.0
BAR_WIDTH = 20
NAME_WIDTH = 10
BLINK_LEVELS = (1.0, 0.1, 1.0, 0.1, 1.0)
BLINK_STEP_SECONDS = 0.4


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="decibulb",
        description="Turn an old mixer into a light switch.",
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

    discover = commands.add_parser("discover", help="find nearby lights")
    discover.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_SCAN_SECONDS,
        help=f"seconds to scan (default: {DEFAULT_SCAN_SECONDS:g})",
    )
    discover.add_argument(
        "--blink",
        action="store_true",
        help="blink each light one at a time so you can tell which is which",
    )
    discover.set_defaults(func=cmd_discover)

    run = commands.add_parser("run", help="control your devices from the board")
    run.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"config file (default: {DEFAULT_CONFIG_PATH})",
    )
    run.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="show timing for every command; -vv also shows Bluetooth library messages",
    )
    run.set_defaults(func=cmd_run)

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


def cmd_discover(args: argparse.Namespace) -> int:
    """List nearby lights, then optionally blink each one.

    Args:
        args: Parsed arguments with `timeout` and `blink`.

    Returns:
        Exit code.

    Raises:
        OSError: If Bluetooth is unavailable.
    """
    try:
        return asyncio.run(_discover(args.timeout, args.blink))
    except KeyboardInterrupt:
        print()
        return 0


async def _discover(timeout: float, blink: bool) -> int:
    """Scan, print a table of lights, and blink them if asked."""
    print(f"Scanning for Govee lights for {timeout:g} seconds...")
    lights = sorted(await discover_bulbs(timeout), key=lambda light: light.name)

    if not lights:
        print("No lights found. Check that they're powered on and not connected to a phone.")
        return 0

    print(f"\n{'MODEL':<8}{'ADDRESS':<20}{'NAME':<24}SIGNAL")
    for light in lights:
        signal = f"{light.rssi} dBm" if light.rssi is not None else "?"
        print(f"{light.sku:<8}{light.address:<20}{light.name:<24}{signal}")
    print(f"\nFound {len(lights)} light{'s' if len(lights) != 1 else ''}.")

    if blink:
        for index, light in enumerate(lights):
            print(f"\nBlinking {light.name}...")
            async with GoveeBleBulb(light.name, light.address) as bulb:
                await bulb.set_power(True)
                for level in BLINK_LEVELS:
                    await bulb.set_brightness(level)
                    await asyncio.sleep(BLINK_STEP_SECONDS)
            if index < len(lights) - 1:
                await asyncio.to_thread(input, "Press Enter for the next light...")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Control devices from a board until interrupted.

    Args:
        args: Parsed arguments with `config` and `verbose` (0, 1, or 2).

    Returns:
        Exit code.

    Raises:
        ConfigError: If the config is missing or invalid.
        OSError: If the board or Bluetooth is unavailable.
    """
    if args.verbose >= 1:
        logging.getLogger("decibulb").setLevel(logging.DEBUG)
    if args.verbose >= 2:
        logging.getLogger("govee_ble_local").setLevel(logging.DEBUG)

    config = load_config(args.config)
    profile = load_profile(config.profile)
    board = MackieBoard(profile, config.port)
    print(f"Listening to {profile.name} on {board.port_name}.")

    try:
        asyncio.run(runner.run(config, profile, board))
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the decibulb CLI.

    Args:
        argv: Arguments to parse. Defaults to sys.argv[1:] when None.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    logging.basicConfig(format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except (ConfigError, OSError) as err:
        print(f"decibulb: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())