# decibulb

[![tests](https://github.com/agulam-coco/decibulb/actions/workflows/tests.yml/badge.svg)](https://github.com/agulam-coco/decibulb/actions/workflows/tests.yml)

Turn an old mixer into a light switch.

https://github.com/user-attachments/assets/5dd3f703-da2c-4fe7-bc86-e792c07a16d9

Plug a mixer or MIDI controller into a Raspberry Pi (or any Linux computer), and its faders control your lights, your speakers, and eventually anything else in your smart home.

**v0.1.0:** faders and buttons control Govee Bluetooth bulbs, and it runs on boot. Controlling room volume is next.

## How it works

```
board (mixer)  →  event ("fader.1 = 0.62")  →  your config  →  device (bulb, volume)
```

- **Board plugins** read the hardware and turn every control into the same standard event. Faders become 0.0 to 1.0, buttons become pressed or released, and encoders become +/- steps.
- **Board profiles** are YAML files that give each control a name, like `fader.1`, `master`, or `play`.
- **Your config** says what each control does, like "fader 1 sets the desk lamp's brightness."
- **Device plugins** send actions like "brightness 0.62" to lights and speakers. Every device accepts the same commands, so the code that connects faders to lights never needs to know what brand of bulb it is.
- **A send queue per device** keeps only the newest value. A fader sends hundreds of values a second, but a bulb can only show a few, so decibulb skips the ones in between instead of falling behind.

Because every board turns into the same events, you can swap mixers or lights without touching the rest of the code.

## Supported hardware

| Type | Hardware | Status |
|---|---|---|
| Board | Zoom R24 (Mackie Control) | All 9 faders, every button, jog wheel |
| Lights | Govee H6008 (Bluetooth) | Power, brightness, color, color temperature |

## Requirements

- A Linux computer with Bluetooth and a free USB port. A Raspberry Pi is the easy pick (tested on a Pi 5 with Raspberry Pi OS), but any Linux machine works: an old laptop, a mini PC, a home server. decibulb only needs BlueZ, the standard Linux Bluetooth stack, which most distros already have.
- Python 3.11 or newer
- A Mackie Control board (tested with the Zoom R24)
- **A real power source for the board.** See [Power](#power) below. This is the most common reason decibulb can't find the board.
- On Python 3.13 or newer, `python-rtmidi` has to compile, so install the build tools first. On Raspberry Pi OS, Debian, or Ubuntu:

  ```bash
  sudo apt install -y libasound2-dev pkg-config python3-dev build-essential
  ```

  On other distros, install the same things under their names there: the ALSA development headers, pkg-config, the Python headers, and a C compiler.

## Power

**Give your board its own power if you can.** If the board runs off your computer's USB port and the port can't supply enough, the board never finishes starting up, and decibulb can't see it. This mostly bites on a Raspberry Pi. A laptop or desktop USB port usually has power to spare.

### Why

A Pi 5 shares a limited amount of USB power across all its ports (600 mA unless it knows its own supply can deliver 5 A). A board like the R24, with a lit screen and LEDs, draws close to that, and more in a burst when it first turns on. If the Pi can't keep up, its voltage dips. The Pi survives, but the board browns out before it shows up as a USB device. Anything else the Pi is running (Docker containers, a NAS, other USB devices) leaves even less to spare, so a setup that worked last week can stop working after you add something.

### Signs your board isn't getting enough power

- `decibulb monitor` says `No MIDI input matching 'R24 MIDI'` and only lists `Midi Through`
- `lsusb` doesn't list the board at all
- `sudo dmesg` shows `over-current change`, or on a Pi, `Undervoltage detected!`
- On a Pi, `vcgencmd get_throttled` prints anything other than `throttled=0x0`

### Options, best first

| Option | Why |
|---|---|
| **The board's own power adapter.** For the R24, the Zoom AD-14 (5V DC, 1A, center positive). | The board doesn't touch the Pi's power at all. Most reliable. |
| **A powered USB hub** between the Pi and the board | The hub has its own plug and powers the board, and the Pi only handles data. Good if you lost the adapter. |
| **Batteries** (the R24 takes 4 AA) | Works anywhere, but they run down. Fine for testing. |
| **The Pi's USB port** | Only on a Pi with an official 27W (5A) supply or a PoE+ HAT rated 4.5 A or more, with `usb_max_current_enable=1` added to `/boot/firmware/config.txt` (then reboot). Even then it's borderline if the Pi is busy with other things. |

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

### 1. Watch your board

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

### 2. Find your lights

```bash
decibulb discover
```

Scans over Bluetooth and lists every Govee light nearby:

```
Scanning for Govee lights for 10 seconds...

MODEL   ADDRESS             NAME                    SIGNAL
H6008   AA:BB:CC:00:00:01   ihoment_H6008_0001      -40 dBm
H6008   AA:BB:CC:00:00:02   ihoment_H6008_0002      -52 dBm
H6008   AA:BB:CC:00:00:03   ihoment_H6008_0003      -55 dBm

Found 3 lights.
```

The names don't tell you which lamp is which, so add `--blink`. Each light flashes one at a time, and you press Enter to move to the next one. Write down which address is which lamp, since you'll need them for your config.

| Option | What it does |
|---|---|
| `--timeout SECONDS` | How long to scan (default: 10) |
| `--blink` | Flash each light one at a time |

**SIGNAL** is Bluetooth strength. Closer to 0 is stronger. Anything above about -70 dBm is solid. If a light is weaker than about -80 dBm, move the Pi closer or expect it to lag.

### 3. Write your config

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

Put in your lights' addresses (in quotes) and choose what each control does:

```yaml
board:
  profile: zoom-r24

brightness_curve: perceptual

devices:
  desk_lamp:
    type: govee_ble
    address: "AA:BB:CC:00:00:01"

controls:
  fader.1:
    action: brightness
    device: desk_lamp
  fader.6:
    action: color_temp
    device: [desk_lamp]
  master:
    action: master_brightness
  solo.1:
    action: toggle_power
    device: desk_lamp
```

| Action | Control | What it does |
|---|---|---|
| `brightness` | fader | Sets brightness. Turns the light on if it was off. |
| `color` | fader | Sweeps through the color wheel |
| `color_temp` | fader | Warm (2700K) at the bottom to cool (6500K) at the top |
| `master_brightness` | fader | Scales every light's brightness at once. No `device` needed. |
| `toggle_power` | button | Turns lights on and off. With several lights, if any are on, all turn off. |

`device` can be one name or a list. **`brightness_curve`** is `perceptual` (the default: more control at the dim end, like a real dimmer) or `linear` (halfway on the fader is 50%).

`config.yaml` is in `.gitignore`, so your addresses never end up on GitHub.

### 4. Run it

```bash
decibulb run
```

```
Connecting desk_lamp...
Connecting corner_lamp...
Connecting wardrobe_lamp...
desk_lamp is on.
corner_lamp is off.
wardrobe_lamp is on.
Ready: 3 of 3 devices connected. Press Ctrl+C to stop.
Zoom R24 connected on R24:R24 MIDI 1 24:0.
```

decibulb is built to keep running when things aren't ready:

- **Lights it can't find** are retried every 30 seconds in the background. When one shows up, its controls start working.
- **The board** doesn't have to be on when decibulb starts. decibulb waits for it, notices when it's turned off, and picks it back up when it comes back.
- **Each light's on/off state** is read when it connects, so the first press of a toggle button does the right thing, and the master fader skips lights that are off.

| Option | What it does |
|---|---|
| `--config PATH` | Config file to use (default: `config.yaml`) |
| `-v` | Show every command sent and how long it took |
| `-vv` | Also show the Bluetooth library's own messages (connects, drops, retries) |

Leave `-v` off for everyday use. Printing dozens of lines a second over SSH can slow things down.

### 5. Start it on boot

`systemd/decibulb.service` runs decibulb as a service: it starts when the computer boots and restarts if it crashes. Raspberry Pi OS and most other Linux distros use systemd. The file assumes your username is `pi` and the repo is in `~/decibulb`. Edit the `User`, `WorkingDirectory`, and `ExecStart` lines if not.

```bash
sudo cp systemd/decibulb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now decibulb
```

| Task | Command |
|---|---|
| See if it's running | `systemctl status decibulb` |
| Watch the log live | `journalctl -u decibulb -f` |
| Restart after changing `config.yaml` or pulling new code | `sudo systemctl restart decibulb` |
| Stop it | `sudo systemctl stop decibulb` |
| Don't start on boot anymore | `sudo systemctl disable decibulb` |

**Stop the service before running decibulb by hand** (`discover`, `run -v`, `scripts/lag_test.py`). A bulb only accepts one connection, so a second copy can't connect to anything.

## Hardware notes

### Zoom R24

- **Interface mode:** press USB, select AUDIO I/F, then EXECUTE. The board shows up as `R24 MIDI 1`. The R24 forgets this when it powers off, so do it again after every restart. `decibulb run` waits for it, so you can do this whenever.
- **Power:** see [Power](#power).
- **Status keys** send a different note in REC, SOLO, and MUTE mode, so they show up as `rec.1` to `rec.8`, `solo.1` to `solo.8`, and `mute.1` to `mute.8`.
- The R24 sends empty jog wheel messages when you switch menus (RHYTHM, EFFECT, USB). decibulb ignores them.

### Govee H6008 bulbs

- These bulbs don't support Govee's LAN API (no LAN Control toggle in the app, and they don't answer LAN scans). Govee's cloud API is limited to about 10 requests per bulb per minute, which is too slow for a fader. decibulb controls them over **Bluetooth** instead, using [govee-ble-local](https://pypi.org/project/govee-ble-local/).
- Find your bulbs' addresses with `decibulb discover --blink`.
- A bulb usually accepts only one Bluetooth connection. Close the Govee app or turn off Bluetooth on your phone if the Pi can't find a bulb. Also make sure no other copy of decibulb is still running (`pgrep -af decibulb`).
- decibulb keeps the Bluetooth connection open the whole time it runs, so there's no reconnect delay when you grab a fader after a pause.
- **A bulb says "got it" much faster than it can show a change.** It acknowledges a command in about 50 ms, but then fades into the new value. Send faster than it can fade, and it builds up its own backlog. The light keeps moving for seconds after you let go, worst on slow fader moves. decibulb sends at most one command every **0.3 seconds** per bulb (`MIN_SEND_INTERVAL` in `throttle.py`), always the newest value. That number came from testing: lower ones lagged on slow moves.
- **Commands that wouldn't change anything are skipped.** Brightness only comes in whole percents, and color temperature is rounded to 50K steps (smaller changes aren't visible). If the bulb is already showing that value, decibulb doesn't send it, so the next real change doesn't wait behind it.
- Brightness only has 100 levels, so very slow fader moves show small steps. That's the bulb, not decibulb.
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

The tests use real MIDI values captured from a Zoom R24, fake boards and devices, and a mocked Bluetooth library, so no hardware is needed to run them.

To test with your real lights but without the board, `scripts/lag_test.py` plays a set of fader moves through the same code as `decibulb run`:

```bash
python scripts/lag_test.py -vv 2>&1 | tee lag.log
```

## Project layout

```
decibulb/
├── .github/workflows/
│   └── tests.yml               runs pytest on every push
├── pyproject.toml              install settings, dependencies, the decibulb command
├── config.example.yaml         starting point for your config.yaml
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
│   ├── devices/
│   │   ├── base.py             the Device base class every device plugin follows
│   │   ├── fake.py             a pretend device for tests and demo mode
│   │   ├── govee_ble.py        Govee lights over Bluetooth
│   │   └── registry.py         turns a config entry into a device
│   ├── config.py               loads and checks config.yaml
│   ├── engine.py               turns events into device commands
│   ├── throttle.py             per-device send queue that keeps only the newest value
│   └── runner.py               connects everything for decibulb run
├── scripts/
│   └── lag_test.py             replays fader moves against real lights
├── systemd/
│   └── decibulb.service        runs decibulb on boot
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_devices.py
    ├── test_engine.py
    ├── test_govee_ble.py
    ├── test_mackie.py
    ├── test_profiles.py
    ├── test_runner.py
    └── test_throttle.py
```

## Roadmap

- [x] Read the Zoom R24 over Mackie Control
- [x] `decibulb monitor`
- [x] Govee Bluetooth device plugin
- [x] `decibulb discover`: find lights and blink them to tell which is which
- [x] Config file and `decibulb run`: faders control lights
- [x] Read each light's real on/off state when decibulb starts
- [x] Skip commands that wouldn't change the light
- [x] Wait for the board and retry missing lights in the background
- [x] Run as a service so it starts on boot
- [x] Tests on GitHub Actions, demo, v0.1.0 release
- [ ] Room volume: Alexa plays through the Pi, one fader sets the volume
- [ ] Home Assistant and MQTT devices, plain MIDI CC boards

## License

MIT
