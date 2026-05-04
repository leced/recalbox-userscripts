# How to Install and Uninstall Userscripts

## Installing a userscript

### Method 1 — Copy via network share (Windows)

1. Connect to your Recalbox shared folder by opening `\\recalbox\share\userscripts` in Windows Explorer. See [this tutorial](https://www.youtube.com/watch?v=hs4iaOh4-xg) for how to connect to the Recalbox network share.
2. Copy the userscript file (`.py3`) into that folder.
3. Reboot or restart EmulationStation.

### Method 2 — SCP (macOS / Linux / Windows power-users)

```
scp "script-name[start](sync).py3" root@recalbox.local:/recalbox/share/userscripts/
```

Reboot or restart EmulationStation. The script runs automatically.

No modification to `recalbox.conf` or any other system file is required.

## Uninstalling a userscript

To uninstall, simply delete the script file from the `userscripts` folder using the same method (network share or SSH), then reboot.

Some scripts provide a dedicated **uninstall userscript** — deploy it the same way as a regular script. It will run once, clean up everything, then delete itself.
