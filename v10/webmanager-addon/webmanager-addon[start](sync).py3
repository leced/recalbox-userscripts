#!/usr/bin/env python3
"""
webmanager-addon-action — Custom actions micro-server + web manager patch
==========================================================================
Userscript that runs at EmulationStation startup on the Recalbox.

It does two things:
  1. Installs and starts a micro HTTP API server (port 8081) that exposes
     custom actions like "kill current emulator"
  2. Patches the Recalbox web manager frontend JS to add a
     "Quitter l'emulateur" button in the actions menu (gear icon)

The micro-server runs as a daemon via an init.d script so it survives
EmulationStation restarts. The frontend patch is re-applied at every boot
since Recalbox updates may overwrite the web manager files.

Deploy: copy this file to /recalbox/share/userscripts/
"""

import os
import sys
import stat
import subprocess
import re
import glob

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

API_PORT = 8081
INITD_SCRIPT = "/etc/init.d/S30webmanager-addon"
API_SERVER_PATH = "/recalbox/share/userscripts/webmanager-addon-server.py"
WEB_MANAGER_ASSETS = "/recalbox/web/manager-v3/assets"
PIDFILE = "/var/run/webmanager-addon.pid"

# Emulator binaries are loaded dynamically from configgen.recalboxFiles.recalboxBins
# at server startup (see API_SERVER_CODE). No hardcoded list needed.

# ═══════════════════════════════════════════════════════════════════════════════
# MICRO API SERVER — written to disk, run as daemon
# ═══════════════════════════════════════════════════════════════════════════════

API_SERVER_CODE = r'''#!/usr/bin/env python3
"""
webmanager-addon-server — Micro HTTP API for custom Recalbox actions
Runs on port {port}, exposes:
  GET /api/kill-emulator  — graceful stop then force kill current emulator
  GET /api/status         — check if an emulator is running
  GET /                   — mini web UI
"""

import http.server
import json
import os
import signal
import subprocess
import time
import threading

PORT = {port}

def _load_emulator_binaries():
    """Load emulator binary names from configgen at startup."""
    try:
        from configgen.recalboxFiles import recalboxBins
        # Extract just the binary basename from each path
        bins = set()
        for path in recalboxBins.values():
            bins.add(os.path.basename(path))
        return sorted(bins)
    except Exception:
        return []

EMULATOR_BINARIES = _load_emulator_binaries()

def find_emulator_pids():
    """Find PIDs of running emulator processes."""
    pids = []
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) < 11:
                continue
            pid = parts[1]
            cmd = " ".join(parts[10:])
            for emu in EMULATOR_BINARIES:
                if "/" + emu in cmd or cmd.startswith(emu):
                    try:
                        pids.append(int(pid))
                    except ValueError:
                        pass
                    break
    except Exception:
        pass
    return pids


def kill_emulator():
    """Kill current emulator: SIGTERM, wait 3s, SIGKILL if still alive."""
    pids = find_emulator_pids()
    if not pids:
        return {{"status": "no_emulator", "message": "No emulator is currently running"}}

    # Phase 1: graceful SIGTERM
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    # Wait up to 3 seconds
    deadline = time.time() + 3.0
    while time.time() < deadline:
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)  # check if still alive
                alive.append(pid)
            except ProcessLookupError:
                pass
        if not alive:
            return {{"status": "killed", "message": f"Emulator stopped gracefully (pids: {{pids}})"}}
        time.sleep(0.3)

    # Phase 2: force SIGKILL
    killed_pids = []
    for pid in pids:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
            killed_pids.append(pid)
        except ProcessLookupError:
            pass

    if killed_pids:
        return {{"status": "force_killed", "message": f"Emulator force-killed (pids: {{killed_pids}})"}}
    return {{"status": "killed", "message": f"Emulator stopped (pids: {{pids}})"}}


MINI_UI = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recalbox Actions</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0;
       display: flex; flex-direction: column; align-items: center; padding: 2em; }}
h1 {{ color: #00d4ff; }}
.btn {{ background: #e94560; color: white; border: none; padding: 1em 2em; font-size: 1.2em;
        border-radius: 8px; cursor: pointer; margin: 0.5em; }}
.btn:hover {{ background: #ff6b81; }}
.btn:active {{ background: #c0392b; }}
.btn-info {{ background: #0f3460; }}
.btn-info:hover {{ background: #16537e; }}
#result {{ margin-top: 1em; padding: 1em; background: #16213e; border-radius: 8px;
           min-width: 300px; text-align: center; }}
</style></head><body>
<h1>Recalbox Actions</h1>
<button class="btn" onclick="killEmulator()">Quitter l'emulateur</button>
<button class="btn btn-info" onclick="checkStatus()">Statut</button>
<div id="result"></div>
<script>
async function killEmulator() {{
  document.getElementById('result').textContent = 'Envoi du signal...';
  try {{
    const r = await fetch('/api/kill-emulator');
    const d = await r.json();
    document.getElementById('result').textContent = d.message;
  }} catch(e) {{ document.getElementById('result').textContent = 'Erreur: ' + e; }}
}}
async function checkStatus() {{
  try {{
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('result').textContent = d.running
      ? 'Emulateur en cours (PIDs: ' + d.pids.join(', ') + ')'
      : 'Aucun emulateur en cours';
  }} catch(e) {{ document.getElementById('result').textContent = 'Erreur: ' + e; }}
}}
</script></body></html>"""


class ActionHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/kill-emulator":
            result = kill_emulator()
            self._json_response(result)
        elif self.path == "/api/status":
            pids = find_emulator_pids()
            self._json_response({{"running": len(pids) > 0, "pids": pids}})
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(MINI_UI.encode())
        else:
            self.send_error(404)

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # silent


def run_server():
    server = http.server.HTTPServer(("0.0.0.0", PORT), ActionHandler)
    print(f"recalbox-actions-server listening on port {{PORT}}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
'''.format(port=API_PORT)


# ═══════════════════════════════════════════════════════════════════════════════
# INIT.D SCRIPT — starts/stops the micro API server
# ═══════════════════════════════════════════════════════════════════════════════

INITD_CODE = f'''#!/bin/sh
#
# webmanager-addon — Micro API server for custom Recalbox actions
#

PIDFILE="{PIDFILE}"
DAEMON="{API_SERVER_PATH}"

case "$1" in
  start)
    printf "Starting webmanager-addon: "
    start-stop-daemon -S -q -m -p "$PIDFILE" -b --exec /usr/bin/python3 -- "$DAEMON"
    echo "OK"
  ;;
  stop)
    printf "Stopping webmanager-addon: "
    start-stop-daemon -K -q -p "$PIDFILE"
    rm -f "$PIDFILE"
    echo "OK"
  ;;
  restart|reload)
    "$0" stop
    sleep 1
    "$0" start
  ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "webmanager-addon is running"
    else
      echo "webmanager-addon is not running"
    fi
  ;;
  *)
    echo "Usage: $0 {{start|stop|restart|status}}"
    exit 1
  ;;
esac
exit 0
'''


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND PATCH — inject "Kill Emulator" button into web manager
# ═══════════════════════════════════════════════════════════════════════════════

def patch_frontend():
    """Patch the web manager MainLayout JS to add a Kill Emulator button."""
    # Find the MainLayout JS file
    pattern = os.path.join(WEB_MANAGER_ASSETS, "MainLayout-*.js")
    matches = glob.glob(pattern)
    if not matches:
        print("[webmanager-addon] MainLayout JS not found, skipping frontend patch")
        return False

    layout_path = matches[0]
    with open(layout_path, "r", encoding="utf-8") as f:
        content = f.read()

    es_stop_marker = ',i($,{onClick:u[6]||(u[6]=g=>o(h)())'
    addon_start = '/*WMA*/'
    addon_end = '/*~WMA*/'

    # Always start from the pristine original (squashfs lower layer)
    # This guarantees a clean slate regardless of previous patch state.
    original_path = layout_path.replace("/recalbox/", "/overlay/lower/recalbox/", 1)
    if os.path.exists(original_path):
        with open(original_path, "r", encoding="utf-8") as f:
            content = f.read()
        print("[webmanager-addon] Loaded pristine MainLayout JS from squashfs")
    else:
        # Fallback: strip previous patch using markers
        if addon_start in content:
            content = re.sub(re.escape(addon_start) + '.*?' + re.escape(addon_end), '', content)
            print("[webmanager-addon] Removed previous frontend patch")

    # Inject a "Kill Emulator" button before the ES stop button in the actions menu.
    # The button calls our micro API server to gracefully/force kill the running emulator.
    # Uses Quasar Notify (via Vue app $q.notify) instead of alert() for feedback.
    # i18n: detects locale at click time to show the right message.
    i18n_helper = (
        'function _l(){'
        'try{var a=document.querySelector("#q-app").__vue_app__;'
        'return(a.config.globalProperties.$i18n.locale||"en").substr(0,2)}'
        'catch(e){return"en"}}'
    )
    notify_helper = (
        'function _n(m,t){'
        'var q=document.querySelector("#q-app");'
        'if(q&&q.__vue_app__){'
        'var nf=q.__vue_app__.config.globalProperties.$q.notify;'
        'nf({message:m,type:t,icon:t==="positive"?"mdi-check-bold":"mdi-alert-outline"})'
        '}else{alert(m)}}'
    )
    # Translated messages for kill-emulator responses
    msgs_helper = (
        'var _m={'
        'fr:{no_emulator:"Aucun \\u00e9mulateur en cours",killed:"\\u00c9mulateur arr\\u00eat\\u00e9",force_killed:"\\u00c9mulateur arr\\u00eat\\u00e9 (forc\\u00e9)",error:"Erreur"},'
        'en:{no_emulator:"No emulator running",killed:"Emulator stopped",force_killed:"Emulator stopped (forced)",error:"Error"}};'
    )
    kill_button_code = (
        ',i($,{onClick:function(){' + i18n_helper + notify_helper + msgs_helper
        + 'var lg=_l(),mg=_m[lg]||_m.en;'
        + 'fetch("http://"+window.location.hostname+'
        '":' + str(API_PORT) + '/api/kill-emulator").then(function(r){return r.json()}).then('
        'function(d){_n(mg[d.status]||d.message,d.status==="no_emulator"?"warning":"positive")})'
        '.catch(function(e){_n(mg.error+": "+e,"negative")})},'
        'color:o(S).isActive?"dark-grey-stronger":"secondary",'
        'icon:"mdi-close-circle",label:"Quitter l\\u0027emulateur",'
        '"label-position":"left",square:""},null,8,["color"])'
    )

    count = content.count(es_stop_marker)

    if count == 0:
        print("[webmanager-addon] Could not find ES stop button pattern in MainLayout JS")
        return False

    new_content = content.replace(es_stop_marker, addon_start + kill_button_code + addon_end + es_stop_marker)

    with open(layout_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[webmanager-addon] Frontend patched: {count} button(s) injected in MainLayout JS")
    return True


def patch_index_html():
    """Inject an observer script into index.html that polls emulator status
    when the gear menu is open, and toggles the kill-emulator button state."""
    index_path = os.path.join(os.path.dirname(WEB_MANAGER_ASSETS), "index.html")
    if not os.path.exists(index_path):
        print("[webmanager-addon] index.html not found, skipping observer patch")
        return False

    # Always start from the pristine original (squashfs lower layer)
    original_index = index_path.replace("/recalbox/", "/overlay/lower/recalbox/", 1)
    if os.path.exists(original_index):
        with open(original_index, "r", encoding="utf-8") as f:
            content = f.read()
        print("[webmanager-addon] Loaded pristine index.html from squashfs")
    else:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Fallback: strip previous observer patch
        if "webmanager-addon-observer" in content:
            content = re.sub(r'<script id="webmanager-addon-observer">.*?</script>', '', content, flags=re.DOTALL)
            print("[webmanager-addon] Removed previous observer script from index.html")

    # The observer script:
    # - Uses MutationObserver to detect when QFabAction buttons appear (gear menu open)
    # - When our kill-emu button is visible, polls /api/status to check emulator state
    # - Toggles disabled class + opacity on the button accordingly
    # - Updates button label based on active locale (fr/en)
    # - Stops polling when the menu closes (button removed from DOM)
    observer_script = '''<script id="webmanager-addon-observer">
(function(){
  var polling=null, API="http://"+window.location.hostname+":''' + str(API_PORT) + '''";
  var labels={fr:"Quitter l\\u0027\\u00e9mulateur",en:"Quit emulator"};
  window.__emuRunning=false;
  function getLang(){
    try{var a=document.querySelector("#q-app").__vue_app__;
    return(a.config.globalProperties.$i18n.locale||"en").substr(0,2)}
    catch(e){return"en"}
  }
  function checkStatus(){
    var lang=getLang();
    fetch(API+"/api/status").then(function(r){return r.json()}).then(function(d){
      window.__emuRunning=d.running;
      document.querySelectorAll(".q-fab__actions .q-btn").forEach(function(btn){
        if(btn.querySelector(".mdi-close-circle")){
          var lbl=btn.querySelector(".q-btn__content span");
          if(lbl) lbl.textContent=labels[lang]||labels.en;
          if(d.running){
            btn.classList.remove("disabled");
            btn.style.opacity="1";btn.style.pointerEvents="auto";
          }else{
            btn.classList.add("disabled");
            btn.style.opacity="0.35";btn.style.pointerEvents="none";
          }
        }
      });
    }).catch(function(){});
  }
  new MutationObserver(function(){
    var found=false;
    document.querySelectorAll(".q-fab__actions .q-btn").forEach(function(btn){
      if(btn.querySelector(".mdi-close-circle")) found=true;
    });
    if(found&&!polling){
      checkStatus();
      polling=setInterval(checkStatus,3000);
    }else if(!found&&polling){
      clearInterval(polling);polling=null;
    }
  }).observe(document.body,{childList:true,subtree:true});
})();
</script>'''

    new_content = content.replace("</body>", observer_script + "</body>")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("[webmanager-addon] index.html patched with observer script")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — Install and start everything
# ═══════════════════════════════════════════════════════════════════════════════

def remount_rw():
    subprocess.run(["mount", "-o", "remount,rw", "/"], check=False)

def remount_ro():
    subprocess.run(["mount", "-o", "remount,ro", "/"], check=False)

def main():
    print("[webmanager-addon] Starting setup...")

    try:
        remount_rw()

        # 1. Write the micro API server script
        with open(API_SERVER_PATH, "w") as f:
            f.write(API_SERVER_CODE)
        os.chmod(API_SERVER_PATH, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        print(f"[webmanager-addon] API server written to {API_SERVER_PATH}")

        # 2. Write the init.d script
        with open(INITD_SCRIPT, "w") as f:
            f.write(INITD_CODE)
        os.chmod(INITD_SCRIPT, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        print(f"[webmanager-addon] Init script written to {INITD_SCRIPT}")

        # 3. Patch the web manager frontend
        patch_frontend()

        # 4. Patch index.html with observer script (status polling)
        patch_index_html()

    finally:
        remount_ro()

    # 4. Start the server (if not already running)
    result = subprocess.run([INITD_SCRIPT, "status"], capture_output=True, text=True, check=False)
    if "not running" in result.stdout:
        subprocess.run([INITD_SCRIPT, "start"], check=False)
        print("[webmanager-addon] API server started")
    else:
        subprocess.run([INITD_SCRIPT, "restart"], check=False)
        print("[webmanager-addon] API server restarted")

    print("[webmanager-addon] Setup complete")


if __name__ == "__main__":
    main()
