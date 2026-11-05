# decibulb

Turn an old mixer into a light switch.

Plug a mixer or MIDI controller into a Raspberry Pi, and its faders control your lights, your speakers, and eventually anything else in your smart home.

> 🚧 Work in progress. Reading a board works (`decibulb monitor`) and the Govee bulb plugin works. Connecting faders to lights is next.

## How it works

```
board (mixer)  →  event ("fader.1 = 0.62")  →  your config  →  device (bulb, volume)
```

- **Board plugins** read the hardware and turn every control into the same standard event. Faders become 0.0 to 1.0, buttons become pressed or released, and encoders become +/- steps.
- **Board profiles** are YAML files that give each control a name, like `fader.1`, `master`, or `play`.
- **Device plugins** send actions like "brightness 0.62" to lights and speakers. Every device accepts the same commands, so the code that connects faders to lights never needs to know what brand of bulb it is.

Because every board turns into the same events, you can swap mixers or lights without touching the rest of the code.

## Supported hardware

| Type | Hardware | Status |
|---|---|---|
| Board | Zoom R24 (Mackie Control) | ✅ All 9 faders, every button, jog wheel |
| Lights | Govee H6008 (Bluetooth) | ✅ Power, brightness, color, color temperature |

## Requirements

- A Raspberry Pi running Raspberry Pi OS (tested on a Pi 5)
- Python 3.11 or newer
- A Mackie Control board (tested with the Zoom R24)
- On Python 3.13 or newer, `python-rtmidi` has to compile, so install the build tools first:

  ```bash
  sudo apt install -y libasound2-dev pkg-config python3-dev build-essential
  ```

## Install

```bash
git clone https://github.com/agulam-coco/decibulb.git
cd decibulb
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
decibulb --version
```

Run `source .venv/bin/activate` again in every new terminal.

## Usage

### Watch your board

```bash
decibulb monitor
```

Move faders, press buttons, and spin knobs to see live events:

```
Listening to Zoom R24 on R24:R24 MIDI 1 24:0. Press Ctrl+C to stop.
fader.1    ████████████░░░░░░░░ 0.62
master     ████████████████████ 1.00
play       pressed
play       released
jog        → +1
```

| Option | What it does |
|---|---|
| `--profile NAME` | Board profile to use (default: `zoom-r24`) |
| `--port PORT` | Exact MIDI port name, if auto-detect picks the wrong one |
| `--raw` | Show the raw MIDI message next to each event |

Lines marked `skipped` are messages that didn't produce an event, either because the profile doesn't name that control yet or because the message carried no change.

## Hardware notes

### Zoom R24

- **Interface mode:** press USB, select AUDIO I/F, then EXECUTE. The board shows up as `R24 MIDI 1`.
- **Power:** the R24 can run on USB power alone in interface mode, but a Pi 5 limits USB current unless it's on a 5A supply. If `dmesg` shows repeated `over-current change` lines:
  - If your Pi has an official 27W supply or a PoE+ HAT rated 4.5A or more, add `usb_max_current_enable=1` to the bottom of `/boot/firmware/config.txt` and reboot.
  - Otherwise, use a powered USB hub or the Zoom AD-14 adapter (5V DC, 1A, center positive).
- **Status keys** send a different note in REC, SOLO, and MUTE mode, so they show up as `rec.1` to `rec.8`, `solo.1` to `solo.8`, and `mute.1` to `mute.8`.
- The R24 sends empty jog wheel messages when you switch menus (RHYTHM, EFFECT, USB). decibulb ignores them.

### Govee H6008 bulbs

- These bulbs don't support Govee's LAN API (no LAN Control toggle in the app, and they don't answer LAN scans). Govee's cloud API is limited to about 10 requests per bulb per minute, which is too slow for a fader. decibulb controls them over **Bluetooth** instead, using [govee-ble-local](https://pypi.org/project/govee-ble-local/).
- A bulb usually accepts only one Bluetooth connection. Turn off Bluetooth on your phone if the Pi can't find a bulb.
- decibulb keeps the Bluetooth connection open the whole time it runs, so there's no reconnect delay when you grab a fader after a pause.
- Each bulb takes about **10 updates per second** over Bluetooth. Fast enough for a fader, as long as decibulb only sends the latest value instead of every tiny step.
- The dimmest setting is 1%. Govee bulbs can't go to 0% brightness, so "off" is a separate power command.
- Color temperature ranges from 2700K (warm) to 6500K (cool). Values outside that are clamped.
- Avoid power cycling them quickly. The H6008 reportedly factory-resets after four quick power cycles in a row.

## Adding your board

If your board speaks Mackie Control, you can add it without writing code:

1. Run `decibulb monitor --raw` and move every control. Write down the channel or note each one sends.
2. Copy `src/decibulb/profiles/zoom-r24.yaml` to `src/decibulb/profiles/<your-board>.yaml` and fill in your numbers.
3. Run `decibulb monitor --profile <your-board>` to check it.
4. Run `pytest`. Every profile is checked automatically.

Support for plain MIDI CC controllers (Korg nanoKONTROL, Akai MIDImix, and similar) is planned.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The tests use real MIDI values captured from a Zoom R24, so no hardware is needed to run them.

## Project layout

```
decibulb/
├── pyproject.toml              install settings, dependencies, the decibulb command
├── README.md
├── LICENSE
├── src/decibulb/
│   ├── __init__.py             package version
│   ├── cli.py                  the decibulb command
│   ├── events.py               the standard ControlEvent every board produces
│   ├── profiles.py             loads board profiles
│   ├── profiles/
│   │   └── zoom-r24.yaml       control names for the Zoom R24
│   ├── boards/
│   │   └── mackie.py           reads Mackie Control boards
│   └── devices/
│       ├── base.py             the Device base class every device plugin follows
│       ├── fake.py             a pretend device for tests and demo mode
│       └── govee_ble.py        Govee lights over Bluetooth
└── tests/
    ├── test_cli.py
    ├── test_devices.py
    ├── test_mackie.py
    └── test_profiles.py
```

## Roadmap

- [x] Read the Zoom R24 over Mackie Control
- [x] `decibulb monitor`
- [x] Govee Bluetooth device plugin
- [ ] `decibulb discover`: find bulbs on the command line
- [ ] Config file and `decibulb run`: faders control lights
- [ ] Room volume: Alexa plays through the Pi, one fader sets the volume
- [ ] Home Assistant and MQTT devices, plain MIDI CC boards

## License

MIT