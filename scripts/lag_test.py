"""Replay fader moves against the real lights, with no board attached.

Runs the same code as `decibulb run`, but a scripted board stands in for
the mixer. Useful for reproducing lag while away from the board.

Usage:
    python scripts/lag_test.py [--config PATH] [--idle MINUTES] [-v | -vv]
"""

import argparse
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from decibulb import runner
from decibulb.config import DEFAULT_CONFIG_PATH, load_config
from decibulb.events import ControlEvent, ControlKind
from decibulb.profiles import load_profile

SWEEP_SECONDS = 1.0
SWEEP_STEPS = 100  # about what a real fader sends in a quick move
SETTLE_SECONDS = 10.0  # long enough for a stuck command to finish and log


class ScriptedBoard:
    """Stand-in board that plays a fixed sequence of fader moves."""

    def __init__(self, idle_seconds: float) -> None:
        """Create the script.

        Args:
            idle_seconds: How long to leave the lights alone mid-test.
        """
        self.idle_seconds = idle_seconds
        self._start = time.monotonic()

    async def listen(self) -> AsyncIterator[tuple[None, ControlEvent]]:
        """Yield fader events in the order a person would make them."""
        await asyncio.sleep(2)
        self._mark("fresh: color temp (fader.6) sweep")
        async for item in self._sweep("fader.6", 0.0, 1.0):
            yield item
        await self._settle()

        self._mark(f"idle: leaving the lights alone for {self.idle_seconds:g} s")
        await asyncio.sleep(self.idle_seconds)

        self._mark("after idle: color temp (fader.6) sweep")
        async for item in self._sweep("fader.6", 1.0, 0.0):
            yield item
        await self._settle()

        self._mark("after idle: brightness (fader.1) sweep")
        async for item in self._sweep("fader.1", 0.2, 1.0):
            yield item
        await self._settle()

        self._mark("after idle: color (fader.5) sweep")
        async for item in self._sweep("fader.5", 0.0, 1.0):
            yield item
        await self._settle()
        self._mark("done")

    async def _sweep(
        self, control: str, start: float, end: float
    ) -> AsyncIterator[tuple[None, ControlEvent]]:
        """Move one fader smoothly from `start` to `end`."""
        for step in range(SWEEP_STEPS + 1):
            value = start + (end - start) * step / SWEEP_STEPS
            yield None, ControlEvent(control, ControlKind.FADER, value)
            await asyncio.sleep(SWEEP_SECONDS / SWEEP_STEPS)

    async def _settle(self) -> None:
        """Pause so the lights catch up before the next move."""
        self._mark(f"fader released, waiting {SETTLE_SECONDS:g} s")
        await asyncio.sleep(SETTLE_SECONDS)

    def _mark(self, text: str) -> None:
        """Print a timestamped marker line so the log is easy to read."""
        print(f"\n=== [{time.monotonic() - self._start:7.1f} s] {text} ===", flush=True)


def main() -> None:
    """Parse arguments and run the scripted test."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--idle", type=float, default=5.0, help="minutes to sit idle mid-test (default: 5)"
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.verbose >= 1:
        logging.getLogger("decibulb").setLevel(logging.DEBUG)
    if args.verbose >= 2:
        logging.getLogger("govee_ble_local").setLevel(logging.DEBUG)

    config = load_config(args.config)
    profile = load_profile(config.profile)
    board = ScriptedBoard(args.idle * 60)
    try:
        asyncio.run(runner.run(config, profile, board))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()