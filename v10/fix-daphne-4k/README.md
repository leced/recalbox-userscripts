# 🕹️ fix-daphne-4k — Hypseus 4K Fix for Recalbox

A Recalbox userscript that fixes Hypseus (Daphne/Singe laserdisc emulator) rendering issues on 4K displays and enables proper mapping of Recalbox display settings to native Hypseus arguments.

## 📋 Overview

| | |
|---|---|
| **Version** | 1.2 |
| **Author** | LeCED |
| **Contact** | noxious@caramail.fr |
| **License** | Free to use and modify |
| **Recalbox** | 10.0 |
| **Hypseus** | 10.0.2 |

## 🎯 What this script fixes

### Issue 1 — Game renders in 1/4 of the screen at 4K

When connected to a 4K TV, the framebuffer is set to 3840x2160, but EmulationStation forces `--resolution 1920x1080` when calling the configgen system. This override is hardcoded in `Emulator.py` and takes precedence over `daphne.videomode` and `global.videomode` from `recalbox.conf`.

As a result, Hypseus renders at 1920x1080 inside a 3840x2160 framebuffer, producing a picture confined to the top-left quarter of the screen.

**Fix:** The script patches `daphneGenerator.py` to read the actual framebuffer resolution from `/sys/class/graphics/fb0/virtual_size` instead of using the ES-forced value.

### Issue 2 — Display settings from recalbox.conf are ignored

The stock `daphneGenerator.py` never reads the `system.Smooth`, `system.ShaderSet`, or `system.Ratio` properties. Settings like `daphne.smooth`, `daphne.shaderset`, and `daphne.ratio` in `recalbox.conf` have no effect on Hypseus.

**Fix:** The script patches `daphneGenerator.py` to map Recalbox settings to native Hypseus arguments:

| recalbox.conf setting | Hypseus argument |
|---|---|
| `daphne.smooth=1` | `-linear_scale` |
| `daphne.shaderset=scanlines` | `-scanlines` |
| `daphne.ratio=4/3` | `-force_aspect_ratio` |
| `daphne.ratio=full` | `-ignore_aspect_ratio` |

### Issue 3 — Scanlines invisible at 4K

Even when `-scanlines` is correctly passed to Hypseus, the default `scanline_shunt` value of 2 is far too fine to be perceptible at 2160 vertical lines. The scanlines are technically rendered but effectively invisible on a 4K display.

**Fix:** When the framebuffer height is >= 2160, the script automatically adds `-scanline_shunt 4 -scanline_alpha 200` for clearly visible scanlines. At lower resolutions, Hypseus defaults are preserved.

## ⚠️ Warning — Bilinear filtering performance

While `daphne.smooth=1` is correctly mapped to the Hypseus `-linear_scale` argument, **enabling it causes severe performance degradation on Raspberry Pi 5**. Bilinear filtering at 4K resolution is too demanding for the RPi5 GPU and results in significant slowdowns during gameplay.

**Recommendation:** Keep `daphne.smooth=0` (or `global.smooth=0`) unless running at a lower resolution.

## 🖥️ Compatibility

> **This script was written and tested exclusively on Raspberry Pi 5 running Recalbox 10.0 with a 4K TV.**
>
> The author does not know whether it is compatible with other hardware (Pi 4, Pi 3, x86, Odroid, etc.) or other Recalbox versions. The patched code patterns are specific to Recalbox 10.0 and may differ on other releases. **Use on other systems at your own risk.**

## 📦 Installation

1. Copy the script to the Recalbox userscripts directory:

```
scp fix-daphne-4k[start](sync).py3 root@recalbox.local:/recalbox/share/userscripts/
```

2. That's it. The script runs automatically every time EmulationStation starts.

No modification to `recalbox.conf`, `.commands` files, or any other system file is required.

## ⚙️ How it works

The script leverages the Recalbox [userscripts system](https://wiki.recalbox.com/en/advanced-usage/scripts-on-emulationstation-events). The filename convention `fix-daphne-4k[start](sync).py3` means:

- `[start]` — executes when EmulationStation starts
- `(sync)` — runs synchronously (blocking, before ES is fully loaded)
- `.py3` — interpreted as Python 3

At each ES startup, the script:

1. Reads the stock `daphneGenerator.py` from the Recalbox overlay filesystem
2. Applies two targeted string replacements (Fix 1 and Fix 2)
3. Remounts `/` as read-write, writes the patched file, remounts as read-only
4. If the patches are already present, does nothing (idempotent)

This approach survives Recalbox updates: when an update restores the original `daphneGenerator.py`, the script simply re-applies the patches at the next boot.

### Patched file

```
/usr/lib/python3.11/site-packages/configgen/generators/daphne/daphneGenerator.py
```

### Resolution source

```
/sys/class/graphics/fb0/virtual_size
```

## 🔧 Configuration

The recommended `recalbox.conf` settings for Daphne on a 4K display:

```ini
# Use Hypseus emulator (default for Daphne games)
daphne.emulator=hypseus

# Scanlines enabled — mapped to -scanlines by the script
# At 4K, -scanline_shunt 4 and -scanline_alpha 200 are added automatically
daphne.shaderset=scanlines

# Smooth / bilinear filtering — mapped to -linear_scale
# WARNING: causes severe slowdowns on RPi5 at 4K. Keep disabled.
daphne.smooth=0

# Aspect ratio — auto uses MPEG header default
# 4/3 maps to -force_aspect_ratio, full maps to -ignore_aspect_ratio
daphne.ratio=auto

# Leave videomode empty — the script reads the framebuffer directly
daphne.videomode=
```

### Fine-tuning scanlines

If the auto-detected scanline values (shunt=4, alpha=200) are not to your liking, you can override them via `daphne.args` in `recalbox.conf`. Arguments passed through `daphne.args` are appended after the script's values, and Hypseus uses the last occurrence:

```ini
# Example: thicker and darker scanlines
daphne.args=-scanline_shunt 6 -scanline_alpha 255
```

| Parameter | Range | Description |
|---|---|---|
| `-scanline_shunt` | 2–10 | Scanline thickness. Higher = thicker lines. Default: 2 (auto: 4 at 4K) |
| `-scanline_alpha` | 1–255 | Scanline opacity. Higher = darker. Default: unset (auto: 200 at 4K) |

## 📁 File structure

```
/recalbox/share/userscripts/
└── fix-daphne-4k[start](sync).py3    # The userscript (this project)
└── README.md                          # This file
```

## 📝 Changelog

### v1.2 — 4K scanline visibility
- When scanlines are enabled and framebuffer height >= 2160, automatically adds `-scanline_shunt 4` and `-scanline_alpha 200`
- Resolution detection now stores `fb_height` for use by the scanline logic
- Added compatibility notice, `-linear_scale` performance warning, and changelog

### v1.1 — Cleanup
- Restored all modified files (daphneGenerator.py, .commands, recalbox.conf) to stock
- Script now handles all patching autonomously at each ES startup

### v1.0 — Initial release
- Framebuffer resolution detection replacing ES-forced 1920x1080
- Display settings mapping (smooth, shaderset, ratio) to native Hypseus arguments

## 🙏 Acknowledgements

- [Hypseus Singe](https://github.com/DirtBagXon/hypseus-singe) by DirtBagXon
- [Recalbox](https://www.recalbox.com/) team
