#!/usr/bin/env python3
"""
Fix daphneGenerator.py to use framebuffer resolution
instead of EmulationStation-forced resolution, and map
Recalbox display settings to native Hypseus arguments.

Recalbox version: 10.0
Tested on: Raspberry Pi 5 with 4K TV

Author: LeCED
Contact: noxious@caramail.fr
Version: 1.2

===============================================================================
COMPATIBILITY
===============================================================================

This script was written and tested exclusively on Raspberry Pi 5 running
Recalbox 10.0 with a 4K TV. The author does not know if it is compatible
with other hardware (Pi 4, Pi 3, x86, Odroid, etc.) or other Recalbox
versions. Use on other systems at your own risk. The patched code patterns
may differ on other Recalbox releases.

===============================================================================
WARNING: -linear_scale (daphne.smooth=1)
===============================================================================

While daphne.smooth=1 is correctly mapped to the Hypseus -linear_scale
argument, enabling it causes severe performance issues on Raspberry Pi 5.
Bilinear filtering at 4K resolution is too demanding for the RPi5 GPU and
results in terrible slowdowns during gameplay. It is strongly recommended
to keep daphne.smooth=0 (or global.smooth=0) unless you are running at a
lower resolution.

===============================================================================
THE ISSUES
===============================================================================

1. EmulationStation forces 1920x1080 resolution when launching Hypseus
   (Daphne emulator), ignoring the actual framebuffer resolution.
   This causes the game to render in only a quarter of the screen on
   4K displays.

2. Display settings from recalbox.conf (smooth, shaderset, ratio) are
   not passed to Hypseus as native arguments.

3. Hypseus scanlines are invisible at 4K because the default
   scanline_shunt of 2 is too fine at 2160 vertical lines.

===============================================================================
THE FIXES
===============================================================================

1. Reads the real framebuffer resolution from
   /sys/class/graphics/fb0/virtual_size instead of using the
   ES-forced resolution.

2. Maps recalbox.conf settings to Hypseus arguments:
   - daphne.smooth=1            -> -linear_scale  (see WARNING above)
   - daphne.shaderset=scanlines -> -scanlines
   - daphne.ratio=4/3           -> -force_aspect_ratio
   - daphne.ratio=full          -> -ignore_aspect_ratio

3. At 4K (framebuffer height >= 2160), automatically adds
   -scanline_shunt 4 and -scanline_alpha 200 for visible scanlines.
   At lower resolutions, Hypseus defaults are preserved (shunt=2).

===============================================================================
CHANGELOG
===============================================================================

v1.0 - Initial release
    - Fix 1: Framebuffer resolution detection replacing ES-forced 1920x1080
    - Fix 2: Display settings mapping (smooth, shaderset, ratio)

v1.1 - Cleanup
    - Restored original daphneGenerator.py, .commands files, and
      recalbox.conf to stock values
    - Script now handles all patching autonomously at each ES startup

v1.2 - 4K scanline visibility
    - Fix 2 updated: when scanlines are enabled and framebuffer height
      is >= 2160, automatically adds -scanline_shunt 4 -scanline_alpha 200
    - Fix 1 updated: stores fb_height variable for use by scanline logic
    - Added compatibility notice, -linear_scale performance warning,
      and this changelog

===============================================================================
"""
import sys
import subprocess

filepath = "/usr/lib/python3.11/site-packages/configgen/generators/daphne/daphneGenerator.py"

# Fix 1: Framebuffer resolution (stores fb_height for scanline scaling)
ORIGINAL_RESOLUTION = """        from configgen.utils.resolutions import ResolutionParser
        resolution = ResolutionParser(system.VideoMode)
        if resolution.isSet and resolution.selfProcess:
            commandArray.extend(["-x", str(resolution.width), "-y", str(resolution.height)])"""

FIXED_RESOLUTION = """        # Use framebuffer resolution instead of ES-forced resolution
        fb_height = 0
        try:
            with open("/sys/class/graphics/fb0/virtual_size", "r") as fb:
                fb_res = fb.read().strip().split(",")
                if len(fb_res) == 2:
                    commandArray.extend(["-x", fb_res[0], "-y", fb_res[1]])
                    fb_height = int(fb_res[1])
        except Exception:
            # Fallback to ES resolution if framebuffer is not readable
            from configgen.utils.resolutions import ResolutionParser
            resolution = ResolutionParser(system.VideoMode)
            if resolution.isSet and resolution.selfProcess:
                commandArray.extend(["-x", str(resolution.width), "-y", str(resolution.height)])
                fb_height = resolution.height"""

# Fix 2: Display settings mapping (with 4K scanline scaling)
ORIGINAL_DISPLAY = """        if system.CRTEnabled:"""

FIXED_DISPLAY = """        # Map Recalbox display settings to Hypseus native arguments
        if system.Smooth:
            commandArray.extend(["-linear_scale"])
        if system.ShaderSet == "scanlines":
            commandArray.extend(["-scanlines"])
            # At 4K, default scanline_shunt (2) is too fine to see.
            # Use thicker scanlines with higher opacity.
            if fb_height >= 2160:
                commandArray.extend(["-scanline_shunt", "4", "-scanline_alpha", "200"])
        if system.Ratio == "4/3":
            commandArray.extend(["-force_aspect_ratio"])
        elif system.Ratio == "full":
            commandArray.extend(["-ignore_aspect_ratio"])

        if system.CRTEnabled:"""

try:
    with open(filepath, "r") as f:
        content = f.read()

    modified = False

    # Apply fix 1
    if FIXED_RESOLUTION not in content and ORIGINAL_RESOLUTION in content:
        content = content.replace(ORIGINAL_RESOLUTION, FIXED_RESOLUTION)
        modified = True
        print("[fix-daphne-4k] Fix 1 applied: framebuffer resolution")
    elif FIXED_RESOLUTION in content:
        print("[fix-daphne-4k] Fix 1 already applied")
    else:
        print("[fix-daphne-4k] WARNING: Fix 1 pattern not found (Recalbox version may have changed)")

    # Apply fix 2
    if FIXED_DISPLAY not in content and ORIGINAL_DISPLAY in content:
        content = content.replace(ORIGINAL_DISPLAY, FIXED_DISPLAY, 1)
        modified = True
        print("[fix-daphne-4k] Fix 2 applied: display settings with 4K scanline scaling")
    elif FIXED_DISPLAY in content:
        print("[fix-daphne-4k] Fix 2 already applied")
    else:
        print("[fix-daphne-4k] WARNING: Fix 2 pattern not found (Recalbox version may have changed)")

    if modified:
        subprocess.run(["mount", "-o", "remount,rw", "/"], check=True)
        with open(filepath, "w") as f:
            f.write(content)
        subprocess.run(["mount", "-o", "remount,ro", "/"], check=True)
        print("[fix-daphne-4k] All fixes written successfully")
    else:
        print("[fix-daphne-4k] Nothing to do")

except Exception as e:
    subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)
    print("[fix-daphne-4k] ERROR: {}".format(e))
    sys.exit(1)
