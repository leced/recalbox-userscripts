# shell-aliases — Useful Shell Aliases for SSH Sessions

A Recalbox userscript that adds convenient shell aliases, available in every SSH session.

## Overview

| | |
|---|---|
| **Version** | 1.1 |
| **Author** | LeCED |
| **Contact** | noxious@caramail.fr |
| **License** | Free to use and modify |
| **Recalbox** | 10.0.5 |
| **Tested on** | Raspberry Pi 5 |

## Aliases

| Alias | Command | Description |
|---|---|---|
| `ll` | `ls -la` | Long listing with hidden files |
| `cls` | `clear` | Clear the terminal screen |
| `roms` | `cd /recalbox/share/roms` | Go to the ROMs directory |

## Installation

Deploy `shell-aliases[start](sync).py3` to your Recalbox — see [How to install a userscript](../../INSTALL-SCRIPTS.md).

## Adding your own aliases

Edit the `ALIASES` list in the script:

```python
ALIASES = [
    ('ll', 'ls -la'),
    ('cls', 'clear'),
    ('roms', 'ls /recalbox/share/roms'),
]
```

Each entry is a pair `('alias_name', 'command')`. Reboot or restart EmulationStation to apply.

## How it works

Recalbox mounts its root filesystem as read-only. Any change made directly to system files is lost on reboot. This userscript re-applies the aliases at every EmulationStation startup by writing them to `/etc/profile.d/aliases.sh`, which is sourced by `/etc/profile` on every login shell (including SSH sessions).

## Changelog

### v1.1
- Use `/etc/profile.d/aliases.sh` instead of `/root/.bashrc` (not sourced on Recalbox SSH sessions)

### v1.0 — Initial release
- Add `ll` alias
