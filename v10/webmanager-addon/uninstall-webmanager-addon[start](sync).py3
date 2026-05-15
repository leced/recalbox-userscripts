#!/usr/bin/env python3
"""
uninstall-webmanager-addon — Remove webmanager-addon from the Recalbox
========================================================================
One-shot userscript: deploy to /recalbox/share/userscripts/, reboot or
restart EmulationStation. It will uninstall everything then delete itself.

Recalbox version: 10.0
Tested on: Raspberry Pi 5

Author: LeCED
Contact: noxious@caramail.fr
Version: 2.1

===============================================================================
COMPATIBILITY
===============================================================================

This script was written and tested exclusively on Raspberry Pi 5 running
Recalbox 10.0.5. It should work on all architectures but has not been
tested on other systems. The uninstall restores frontend files from the
squashfs lower layer; if the lower directory is not available, a reboot
is required to restore originals. Use on other systems at your own risk.

===============================================================================
WARNING: One-shot self-deleting script
===============================================================================

This script deletes itself after successful execution. If you need to
uninstall again, you must re-deploy the uninstall script first. The script
stops the daemon, removes all generated files, restores patched frontend
files from squashfs, then deletes itself. After the script runs, you should
reboot or restart EmulationStation to ensure everything is clean.

===============================================================================
WHAT IT REMOVES
===============================================================================

- /etc/init.d/S30webmanager-addon         — init.d daemon script
- /recalbox/share/userscripts/webmanager-addon-server.py  — API server
- /var/run/webmanager-addon.pid           — PID file (if stale)
- /recalbox/share/userscripts/webmanager-addon*  — other userscript files
- Patches in /recalbox/web/manager-v3/    — restored from squashfs
- Its own file                            — self-deletes

===============================================================================
CHANGELOG
===============================================================================

v2.1 - Updated with documentation blocks matching main script style
    - Added COMPATIBILITY, WARNING, and CHANGELOG sections
    - Reordered uninstall: init script removed before restore

v1.0 - Initial release
    - Stop daemon, remove files, restore frontend from squashfs
    - Self-deleting one-shot userscript
"""

import os
import glob
import subprocess

SELF = os.path.abspath(__file__)

FILES_TO_REMOVE = [
    "/etc/init.d/S30webmanager-addon",
    "/recalbox/share/userscripts/webmanager-addon-server.py",
    "/var/run/webmanager-addon.pid",
]

USERSCRIPT_PATTERNS = [
    "/recalbox/share/userscripts/webmanager-addon*",
]

MANAGER_DIR = "/recalbox/web/manager-v3"
LOWER_DIR = "/overlay/lower/recalbox/web/manager-v3"


def main():
    print("[uninstall-wma] Starting...")

    # Stop daemon
    if os.path.exists("/etc/init.d/S30webmanager-addon"):
        subprocess.run(["/etc/init.d/S30webmanager-addon", "stop"], capture_output=True)
        print("[uninstall-wma] Daemon stopped")

    # Remount rw
    subprocess.run(["mount", "-o", "remount,rw", "/"], check=False)

    try:
        # Remove known files
        for path in FILES_TO_REMOVE:
            if os.path.exists(path):
                os.remove(path)
                print(f"[uninstall-wma] Removed {path}")

        # Remove webmanager-addon userscripts (but not self yet)
        for pattern in USERSCRIPT_PATTERNS:
            for path in glob.glob(pattern):
                if os.path.abspath(path) == SELF:
                    continue
                os.remove(path)
                print(f"[uninstall-wma] Removed {path}")

        # Restore pristine frontend from squashfs
        if os.path.isdir(LOWER_DIR):
            for src in glob.glob(os.path.join(LOWER_DIR, "assets", "MainLayout-*.js")):
                dst = os.path.join(MANAGER_DIR, "assets", os.path.basename(src))
                with open(src, "r") as f:
                    data = f.read()
                with open(dst, "w") as f:
                    f.write(data)
                print(f"[uninstall-wma] Restored {os.path.basename(src)}")

            src_index = os.path.join(LOWER_DIR, "index.html")
            dst_index = os.path.join(MANAGER_DIR, "index.html")
            if os.path.exists(src_index):
                with open(src_index, "r") as f:
                    data = f.read()
                with open(dst_index, "w") as f:
                    f.write(data)
                print("[uninstall-wma] Restored index.html")
        else:
            print("[uninstall-wma] WARNING: squashfs not found, reboot to restore frontend")

        # Self-delete
        if os.path.exists(SELF):
            os.remove(SELF)
            print(f"[uninstall-wma] Self-deleted")

    finally:
        subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)

    print("[uninstall-wma] Done. webmanager-addon fully removed.")


if __name__ == "__main__":
    main()
