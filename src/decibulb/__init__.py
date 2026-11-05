"""Turn an old mixer into a light switch.

Modules:
    boards: Board plugins that read hardware.
    cli: Command-line entry point.
    config: User configuration file.
    devices: Device plugins that control lights and speakers.
    engine: Turns control events into device commands.
    events: Board-independent control events.
    profiles: Board profiles that name each control.
    runner: Connects everything and routes events to the engine.
    throttle: Sends only the newest command to each device.
"""

__version__ = "0.0.1"