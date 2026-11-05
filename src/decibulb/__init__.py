"""Turn an old mixer into a light switch.

Modules:
    boards: Board plugins that read hardware.
    cli: Command-line entry point.
    config: User configuration file.
    devices: Device plugins that control lights and speakers.
    events: Board-independent control events.
    profiles: Board profiles that name each control.
    throttle: Sends only the newest command to each device.
"""

__version__ = "0.0.1"