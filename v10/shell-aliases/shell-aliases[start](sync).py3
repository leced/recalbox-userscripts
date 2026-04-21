#!/usr/bin/env python3
"""
Add useful shell aliases to /etc/profile.d/aliases.sh so they are
available in every SSH session.

Recalbox version: 10.0
Tested on: Raspberry Pi 5

Author: LeCED
Contact: noxious@caramail.fr
Version: 1.1

===============================================================================
WHY A USERSCRIPT?
===============================================================================

Recalbox mounts its root filesystem as read-only. Any change made directly
to system files would be lost on the next reboot. This userscript re-applies
the aliases at every EmulationStation startup, ensuring they are always
available in SSH sessions.

The aliases are written to /etc/profile.d/aliases.sh, which is sourced by
/etc/profile on every login shell (including SSH sessions).

===============================================================================
ALIASES ADDED
===============================================================================

  ll    ->  ls -la    (long listing with hidden files)

===============================================================================
CHANGELOG
===============================================================================

v1.0 - Initial release
    - Add 'll' alias to /root/.bashrc

v1.1 - Fix target file
    - Use /etc/profile.d/aliases.sh instead of /root/.bashrc
      because .bashrc is not sourced on Recalbox SSH sessions
    - /etc/profile.d/ is sourced by /etc/profile on every login shell

===============================================================================
"""
import sys
import subprocess

ALIASES_PATH = "/etc/profile.d/aliases.sh"

ALIASES = [
    ('ll', 'ls -la'),
]

def alias_line(name, cmd):
    return 'alias {}="{}"'.format(name, cmd)

try:
    try:
        with open(ALIASES_PATH, "r") as f:
            content = f.read()
    except FileNotFoundError:
        content = "#!/bin/sh\n"

    modified = False

    for name, cmd in ALIASES:
        line = alias_line(name, cmd)
        if line not in content:
            content = content.rstrip("\n") + "\n" + line + "\n"
            modified = True
            print("[shell-aliases] Added alias: {}".format(line))
        else:
            print("[shell-aliases] Alias already present: {}".format(line))

    if modified:
        subprocess.run(["mount", "-o", "remount,rw", "/"], check=True)
        with open(ALIASES_PATH, "w") as f:
            f.write(content)
        subprocess.run(["mount", "-o", "remount,ro", "/"], check=True)
        print("[shell-aliases] {} updated successfully".format(ALIASES_PATH))
    else:
        print("[shell-aliases] Nothing to do")

except Exception as e:
    subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)
    print("[shell-aliases] ERROR: {}".format(e))
    sys.exit(1)
