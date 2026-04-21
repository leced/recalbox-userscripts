#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Undo script for fix-daphne-4k[start](sync).py3 - removes the fix and itself.
Author: LeCED
Contact: noxious@caramail.fr
Version: 1.0
Description: Restores the original DaphneGenerator.py from the lower overlay,
             deletes the fix script (fix-daphne-4k[start](sync).py3),
             and then deletes itself.
"""

import os
import shutil
import subprocess
import sys

def remount_rw():
    subprocess.run(["mount", "-o", "remount,rw", "/"], check=False)

def remount_ro():
    subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)

def main():
    upper_path = "/usr/lib/python3.11/site-packages/configgen/generators/daphne/daphneGenerator.py"
    lower_path = "/overlay/lower/usr/lib/python3.11/site-packages/configgen/generators/daphne/daphneGenerator.py"
    fix_script = "/recalbox/share/userscripts/fix-daphne-4k[start](sync).py3"
    undo_script = __file__

    # 1. Restore original from lower overlay if it exists
    if os.path.isfile(lower_path):
        remount_rw()
        try:
            shutil.copy2(lower_path, upper_path)
            print("Restored original DaphneGenerator.py from lower overlay.")
        except Exception as e:
            print(f"Failed to restore DaphneGenerator.py: {e}", file=sys.stderr)
        finally:
            remount_ro()
    else:
        print("Lower overlay copy not found; nothing to restore.", file=sys.stderr)

    # 2. Remove the fix script
    if os.path.isfile(fix_script):
        remount_rw()
        try:
            os.remove(fix_script)
            print(f"Removed fix script: {fix_script}")
        except Exception as e:
            print(f"Failed to remove fix script: {e}", file=sys.stderr)
        finally:
            remount_ro()
    else:
        print("Fix script not present; nothing to remove.", file=sys.stderr)

    # 3. Remove this undo script itself
    if os.path.isfile(undo_script):
        remount_rw()
        try:
            os.remove(undo_script)
            print(f"Removed undo script: {undo_script}")
        except Exception as e:
            print(f"Failed to remove undo script: {e}", file=sys.stderr)
        finally:
            remount_ro()
    else:
        print("Undo script not found; nothing to remove.", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error during rollback: {exc}", file=sys.stderr)
        sys.exit(1)