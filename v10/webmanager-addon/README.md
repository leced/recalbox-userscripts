# 🛠️ webmanager-addon — Custom Actions for the Recalbox Web Manager

A Recalbox userscript that extends the native web manager (port 20666) with custom action buttons and a "Now Playing" music display, powered by a micro HTTP API server.

## 📋 Overview

| | |
|---|---|
| **Version** | 2.1 |
| **Author** | LeCED |
| **Contact** | noxious@caramail.fr |
| **License** | Free to use and modify |
| **Recalbox** | 10.0.5 |
| **Tested on** | Raspberry Pi 5 |

## 🎯 Features

| Feature | Description |
|---|---|
| [Kill Emulator](#-kill-emulator) | Remotely stop a frozen or running emulator from the web manager gear menu |
| [Now Playing Music](#-now-playing-music) | Display the current background music track with album cover art on the home page |

---

### 🎮 Kill Emulator

Adds a "Kill Emulator" button to the gear menu in the web manager. Useful when a game is frozen or you want to exit without physical access to the controller.

The button sends a graceful SIGTERM, waits 3 seconds, then force-kills with SIGKILL if the process is still alive. The button is automatically disabled when no emulator is running.

![Kill Emulator button in the web manager gear menu](../../media/webmanager-addon-kill-emulator.png)

---

### 🎵 Now Playing Music

When no game is running, the "Game" panel on the home page displays the currently playing background music track, including:

- Track title and system/platform (parsed from the filename)
- Album cover art fetched from the [Wikipedia REST API](https://en.wikipedia.org/api/rest_v1/) (client-side, bypasses Cloudflare)
- Automatic updates when the track changes (polled every 10 seconds)
- Loading state while detecting music, and a "no music detected" fallback after repeated failures
- Supports English and French

The music detection works by comparing EmulationStation's file descriptor read positions — the fd whose position changes between two snapshots is the currently playing track.

The cover art search extracts the game name from the track filename and queries the Wikipedia REST API for a matching article thumbnail (trying slug variants `"X (video game)"`, `"X (game)"`, then `"X"`). An internet connection is required for cover art; without it, only the track name is displayed.

> **📝 Note on filenames:** The script supports filenames following the `♪ [SYSTEM] Game Name - Track Title.mp3` convention (system and cover art are extracted automatically). Standard filenames like `My Song.mp3` also work — the full filename is displayed as the track title.

---

## ⚙️ How it works

The script leverages the Recalbox [userscripts system](https://wiki.recalbox.com/en/advanced-usage/scripts-on-emulationstation-events). The filename convention `webmanager-addon[start](sync).py3` means:

- `[start]` — executes when EmulationStation starts
- `(sync)` — runs synchronously (blocking, before ES is fully loaded)
- `.py3` — interpreted as Python 3

At each ES startup, the script does three things:

1. **Installs a micro HTTP API server** (Python, port 8081) that exposes custom action endpoints. The server runs as a daemon via an init.d script (`S30webmanager-addon`) so it survives ES restarts.

2. **Patches the web manager frontend JS** to inject buttons into the gear menu. The patch targets `MainLayout-*.js` in `/recalbox/web/manager-v3/assets/` and is re-applied at each boot to survive Recalbox updates.

3. **Patches index.html** with an observer script that handles the kill-emulator button state polling and the now-playing music display (including cover art lazy loading).

### API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/kill-emulator` | Graceful stop then force kill current emulator |
| `GET /api/status` | Check if an emulator is running (returns PIDs) |
| `GET /api/now-playing` | Detect currently playing music track (~1s response time) |
| `GET /` | Mini standalone web UI |

The mini UI is also accessible directly at `http://recalbox.local:8081/`.

### Recognized Emulators

The server dynamically loads the list of emulator binaries from `configgen.recalboxFiles.recalboxBins` at startup. This means the list is always up to date with the installed Recalbox version, regardless of the hardware platform.

## 📦 Installation

1. Copy the script to the Recalbox userscripts directory:

```
scp "webmanager-addon[start](sync).py3" root@recalbox.local:/recalbox/share/userscripts/
```

2. That's it. The script runs automatically every time EmulationStation starts.

No modification to `recalbox.conf` is required. See [How to install a userscript](../../INSTALL-SCRIPTS.md) for more details.

## 🗑️ Uninstallation

Deploy `uninstall-webmanager-addon[start](sync).py3` to your Recalbox — see [How to install a userscript](../../INSTALL-SCRIPTS.md).

Reboot or restart EmulationStation. The script will:

- Stop and remove the daemon (init.d script + PID file)
- Remove the generated server script and the webmanager-addon userscript
- Restore the original web manager frontend files from squashfs
- Delete itself

## ⚠️ Warning — Init.d daemon staleness

The API server runs as a daemon via `/etc/init.d/S30webmanager-addon`. If the server starts or stops unexpectedly (e.g. due to system sleep or connectivity loss), the PID file at `/var/run/webmanager-addon.pid` may become stale.

The daemon's `status` command checks only the PID file; a stale PID causes the daemon to appear "not running" even when it is, potentially causing duplicate start attempts or refusal to restart.

**Recommendation:** If the server status seems inconsistent, check `/var/run/webmanager-addon.pid` and remove it if the referenced PID no longer exists.

## 🖥️ Compatibility

> **This script was written and tested exclusively on Raspberry Pi 5 running Recalbox 10.0.5.**
>
> It should work on all architectures since the emulator list is loaded dynamically from configgen, but this has not been tested.
>
> The frontend patch targets specific patterns in the minified JS bundle. Different Recalbox versions may use different filenames or code patterns. If the patch fails, the script logs a warning and continues — the API server still works via the mini UI.

## 📁 File structure

### On the host (this repo)

```
webmanager-addon/
├── webmanager-addon[start](sync).py3    # The userscript (all-in-one)
├── uninstall-webmanager-addon[start](sync).py3  # Uninstall userscript (one-shot, self-deleting)
└── README.md                            # This file
```

### On the Recalbox (created by the script)

```
/recalbox/share/userscripts/
├── webmanager-addon[start](sync).py3          # Userscript
└── webmanager-addon-server.py                 # Micro API server (generated)

/etc/init.d/S30webmanager-addon                # Daemon init script (generated)
/recalbox/web/manager-v3/assets/MainLayout-*.js  # Patched frontend
/recalbox/web/manager-v3/index.html              # Patched (observer script)
```

## 📝 Changelog

### v2.1 — Cover art rework, sleep/wake fixes, UI improvements
- Replace khinsider (server-side) with Wikipedia REST API (client-side) — bypasses Cloudflare 403
- Fix slug ordering: `"X (video game)"` first, then `"X (game)"`, bare name last
- Fix cover art race condition: stale Wikipedia responses discarded when track changes
- Fix sleep/wake display bug: detect detached DOM nodes, rebuild now-playing from scratch
- Fix "Loading music…" stuck after wake: recover stale `npContainer` via MutationObserver + poll
- Bigger track title font (`1.25rem` → `1.5rem`) and cover image (`140px` → `180px`)
- Centered now-playing overlay layout (flex centering on `.overlayMessage`)
- Pulsing icon hidden when cover loads successfully
- i18n: localized "Now Playing" label (English/French)
- Remove unused server imports (`urllib`, `re`)
- Updated README with daphne-4k style presentation blocks

### v2.0 — Now Playing Music
- Detect and display currently playing background music track
- Cover art fetched from Wikipedia REST API (client-side, bypasses Cloudflare)
- Loading state and "no music detected" fallback
- English/French i18n support
- New API endpoint: `/api/now-playing`

### v1.0 — Initial release
- Micro HTTP API server with kill-emulator and status endpoints
- Frontend patch injecting "Kill Emulator" button in gear menu
- Mini standalone web UI on port 8081
- SIGTERM + 3s grace period + SIGKILL kill sequence
- Init.d daemon for persistence across ES restarts

## 🙏 Acknowledgements

- [Recalbox](https://www.recalbox.com/) team
- Wikipedia REST API for cover art thumbnails
