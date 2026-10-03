# bettertui

A friendlier terminal UI for [bettercap](https://www.bettercap.org/). It doesn't
replace the engine — it drives the real bettercap over its REST API and gives you
live panels and one-key actions instead of a wall of typed module commands.

```
┌ Hosts ───────────────────────────┬ Modules ──────────┐
│ IP            MAC         Name    │ net.probe   ● on  │
│ 192.168.1.1   aa:bb:..   router   │ net.recon   ● on  │
│ 192.168.1.42  de:ad:..   laptop ◄ │ arp.spoof   ○ off │
│ ...                               │ ...               │
├───────────────────────────────────┴───────────────────┤
│ 12:04:33  endpoint.new  192.168.1.42 detected          │  ← event log
├────────────────────────────────────────────────────────┤
│ bettercap command (e.g. net.show) — Enter to run        │  ← raw command bar
└────────────────────────────────────────────────────────┘
 q Quit  r Refresh  s Scan  a ARP spoof  k Stop  n Sniff  / Command
```

## Why

bettercap is powerful but the REPL makes you memorise module names and
`set module.option value` syntax before anything happens. bettertui keeps the
engine and fixes the interface: you *see* what's discovered and what's running,
and the common workflows are single keys. Anything not wired to a key, you can
still type in the command bar — so you never lose the full power of bettercap.

## Architecture

- **Engine:** bettercap, unchanged, started with its `api.rest` module on.
- **Interface (this repo):** a [Textual](https://textual.textualize.io/) app.
  - `api.py` — async `httpx` client: `session()`, `events()`, `run(cmd)`.
  - `app.py` — the TUI: host/module tables, event log, command bar, and a
    `RECIPES` table mapping keypresses to bettercap command chains.

Keeping the two separate means upstream bettercap updates just work, and the UX
can evolve on its own. Same pattern as `wifite` over `aircrack-ng`.

## Setup

```bash
# 1. bettercap must be installed (https://www.bettercap.org/installation/)
# 2. install bettertui
pip install -e .          # or: pip install -r requirements.txt

# 3. start bettercap with REST on (root, picks your interface)
sudo ./scripts/start-bettercap.sh wlan0 admin s3cret

# 4. in another terminal, launch the UI
bettertui -u admin -p s3cret
```

Options: `--host`, `--port` (default 8081), `-u/--user`, `-p/--password`,
`--https`, `--poll` (refresh seconds).

## Keys

| Key | Action |
|-----|--------|
| `s` | Toggle active host scan (`net.probe`) |
| `a` | ARP-spoof the selected host |
| `k` | Stop ARP spoofing |
| `n` | Toggle sniffer (`net.sniff`) |
| `r` | Refresh now |
| `c` | Clear the event log |
| `/` | Jump to the command bar |
| `q` | Quit |

Select a host with ↑/↓ in the Hosts panel before using `a`.

## Scope / responsible use

ARP spoofing and sniffing are intrusive. Only run them against networks you own
or are explicitly authorised to test.

## Status

MVP. Working: live hosts/modules/events, scan + ARP + sniff recipes, raw command
bar. Next up: a recipe/wizard catalog (guided "capture a handshake", "MITM a
host"), per-host detail view, and optional WebSocket event streaming instead of
polling.
