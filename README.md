# decibulb

Turn an old mixer into a light switch.

Plug a mixer or MIDI controller into a Raspberry Pi, and its faders control your lights, your speakers, and eventually anything else in your smart home.

> 🚧 Early days. Nothing works yet except `decibulb --version`. Follow along as it gets built.

## Setup (for now)

```bash
git clone https://github.com/agulam-coco/decibulb.git
cd decibulb
python3 -m venv .venv          # make a private Python for this project
source .venv/bin/activate      # switch to it (do this in every new terminal)
pip install -e .               # install decibulb in editable mode
decibulb --version             # should print: decibulb 0.0.1
```

## Project layout

```
decibulb/
├── pyproject.toml          how to install the project, and what command it creates
├── README.md               this file
├── LICENSE                 MIT
├── .gitignore              files git should never track
└── src/decibulb/
    ├── __init__.py         marks the package, holds the version number
    └── cli.py              the `decibulb` terminal command
```

## License

MIT
