#!/usr/bin/env python3
"""
webmanager-addon — Custom actions micro-server + web manager patch
===================================================================
Userscript that extends the Recalbox web manager with a "Kill Emulator"
button in the gear menu and a "Now Playing" music display on the home
page, powered by a micro HTTP API server running on port 8081.

Recalbox version: 10.0
Tested on: Raspberry Pi 5

Author: LeCED
Contact: noxious@caramail.fr
Version: 2.3

===============================================================================
COMPATIBILITY
===============================================================================

This script was written and tested exclusively on Raspberry Pi 5 running
Recalbox 10.0.5. It should work on all architectures since the emulator
list is loaded dynamically from configgen, but this has not been tested.
The frontend patch targets specific patterns in the minified JS bundle;
different Recalbox versions may use different filenames or code patterns.
If the patch fails, the script logs a warning and continues — the API
server still works via the mini UI. Use on other systems at your own risk.

===============================================================================
CHANGELOG
===============================================================================

v2.3 - Auto-play, multi-language Wikipedia, page image fallback
    - Auto-play toggle button (mdi-autorenew icon) for continuous playback
      through track changes
    - Multi-language Wikipedia search: uses browser locale (fr/en) to
      choose domain; falls back to en.wikipedia.org if fr returns nothing
    - System name included in search queries on both languages
    - Page image fallback (fetchPageImage): search page images for
      cover/logo when summary thumbnail absent; filters SVG/PDF files
    - Cover search URL logged to browser console for debugging
    - Improved Wikipedia article title matching with length ratio check

v2.2 - Audio streaming, progressive cover search, CORS fixes
    - New endpoint: /api/audio/stream (HTTP Range, threaded server)
    - Play/stop button in now-playing display; stream from byte 0
    - ThreadingMixIn server so streaming doesn't block other endpoints
    - CORS: OPTIONS preflight, Access-Control-Allow-Origin on all responses
    - crossOrigin="anonymous" on audio element to avoid ORB blocking
    - Progressive cover name reduction: strip parentheticals, then last word
    - Fuzzy titleMatch (prefix + suffix >= 70% of search term)
    - Faster initial poll (1.5s first check, then every 10s)
    - Cover image created dynamically — no empty space when no cover found
    - Cyan accent play button colors for better visibility
    - Removed max-width on track title for better wrapping

v2.1 - Cover art rework, sleep/wake fixes, UI improvements
    - Replaced khinsider (server-side) with Wikipedia REST API (client-side)
      to bypass Cloudflare 403
    - Fixed slug ordering: "(video game)" first, then "(game)", bare name last
    - Fixed cover art race condition: stale Wikipedia responses discarded
      when track changes mid-flight
    - Fixed sleep/wake display bug: detect detached DOM nodes, rebuild
      now-playing from scratch
    - Fixed "Loading music..." stuck after wake: recover stale npContainer
      via MutationObserver + poll fallback
    - Increased track title font (1.25rem -> 1.5rem) and cover image
      (140px -> 180px)
    - Centered now-playing overlay layout (flex centering)
    - Pulsing icon hidden when cover loads successfully
    - Added i18n for "Now Playing" label (English/French)
    - Removed unused server imports (urllib, re)

v2.0 - Now Playing Music
    - Detect and display currently playing background music track
    - Cover art fetched from Wikipedia REST API (client-side)
    - Loading state and "no music detected" fallback
    - English/French i18n support
    - New API endpoint: /api/now-playing

v1.0 - Initial release
    - Micro HTTP API server with kill-emulator and status endpoints
    - Frontend patch injecting "Kill Emulator" button in gear menu
    - Mini standalone web UI on port 8081
    - SIGTERM + 3s grace period + SIGKILL kill sequence
    - Init.d daemon for persistence across ES restarts
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
   GET /api/now-playing    — detect currently playing music track (returns filepath + byte_pos)
   GET /api/audio/stream   — stream current track (HTTP Range, CORS, threaded). Params: ?path= (encoded filepath), ?offset= (byte start, default 0)
   GET /                   — mini web UI
"""

import http.server
import json
import os
import signal
import subprocess
import time
import threading
import re
from socketserver import ThreadingMixIn
from urllib.parse import unquote

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


def get_now_playing():
    """Detect the currently playing music track in EmulationStation.

    ES opens all music files at startup but only actively reads one.
    We compare fd read positions with a short delay — the fd whose position
    changes is the track currently being played.
    """
    import sys as _sys
    def _dbg(m): _sys.stderr.write("[wma-dbg] " + m + "\\n")
    try:
        result = subprocess.run(["pidof", "emulationstation"],
                                capture_output=True, text=True)
        pid = result.stdout.strip()
        if not pid:
            _dbg("ES pid not found (pidof returned empty)")
            return {{"playing": False, "track": None}}

        fd_dir = f"/proc/{{pid}}/fd"
        music_fds = {{}}  # fdnum -> target path
        for fdname in os.listdir(fd_dir):
            try:
                target = os.readlink(os.path.join(fd_dir, fdname))
            except OSError:
                continue
            if "/music/" in target:
                music_fds[fdname] = target

        _dbg(f"ES pid={{pid}}, music_fds found={{len(music_fds)}}")
        for fdnum, path in music_fds.items():
            _dbg(f"  fd {{fdnum}} -> {{path}}")

        if not music_fds:
            return {{"playing": False, "track": None}}

        # Read positions (first snapshot)
        def read_positions():
            positions = {{}}
            for fdnum in music_fds:
                try:
                    with open(f"/proc/{{pid}}/fdinfo/{{fdnum}}", "r") as fi:
                        for line in fi:
                            if line.startswith("pos:"):
                                positions[fdnum] = int(line.split()[1])
                                break
                except OSError:
                    pass
            return positions

        pos1 = read_positions()
        _dbg(f"pos1={{pos1}}")
        time.sleep(1)
        pos2 = read_positions()
        _dbg(f"pos2={{pos2}}")

        # The fd whose position changed is the active track
        for fdnum in pos1:
            if fdnum in pos2 and pos2[fdnum] != pos1[fdnum]:
                track_path = music_fds[fdnum]
                # Extract just the filename without extension
                filename = os.path.basename(track_path)
                name = os.path.splitext(filename)[0]
                byte_pos = pos2[fdnum]
                _dbg(f"active track: fd={{fdnum}}, path={{track_path}}")
                return {{"playing": True, "track": name, "file": filename, "filepath": track_path, "byte_pos": byte_pos}}

        _dbg("no fd position changed")
        return {{"playing": False, "track": None}}
    except Exception as e:
        _dbg(f"exception: {{e}}")
        return {{"playing": False, "track": None, "error": str(e)}}


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
        elif self.path == "/api/now-playing":
            result = get_now_playing()
            self._json_response(result)
        elif self.path.startswith("/api/audio/stream"):
            qs = {{}}
            if '?' in self.path:
                for part in self.path.split('?', 1)[1].split('&'):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        qs[k] = v
            filepath = unquote(qs.get('path', ''))
            if not filepath or not filepath.startswith('/recalbox/share/music/'):
                # Fallback: detect via get_now_playing
                np_fb = get_now_playing()
                if np_fb.get("playing") and np_fb.get("filepath"):
                    filepath = np_fb["filepath"]
                else:
                    self.send_response(204)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    return
            if not os.path.exists(filepath):
                self.send_response(204)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            file_size = os.path.getsize(filepath)
            ext = os.path.splitext(filepath)[1].lower()
            content_type = {{
                '.mp3': 'audio/mpeg',
                '.ogg': 'audio/ogg',
                '.wav': 'audio/wav',
                '.flac': 'audio/flac',
                '.aac': 'audio/aac',
                '.m4a': 'audio/mp4',
                '.opus': 'audio/ogg',
            }}.get(ext, 'application/octet-stream')
            range_header = self.headers.get('Range', '')
            start = 0
            end = file_size - 1
            if range_header:
                m = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if m:
                    start = int(m.group(1))
                    if m.group(2):
                        end = int(m.group(2))
            if start > 0:
                self.send_response(206)
                self.send_header('Content-Range', 'bytes {{}}-{{}}/{{}}'.format(start, end, file_size))
            else:
                self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open(filepath, 'rb') as f:
                    f.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk_size = min(65536, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        remaining -= len(chunk)
            except Exception:
                pass
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(MINI_UI.encode())
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Range')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # silent


class ThreadedServer(ThreadingMixIn, http.server.HTTPServer):
    pass


def run_server():
    server = ThreadedServer(("0.0.0.0", PORT), ActionHandler)
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
    es_stop_end = 'label:o(t)("home.system.es.stop"),"label-position":"left",square:""},null,8,["color","label"])'
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

    # Inject a "Kill Emulator" button as the last item in the actions menu (after ES stop).
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

    count = content.count(es_stop_end)

    if count == 0:
        print("[webmanager-addon] Could not find ES stop button pattern in MainLayout JS")
        return False

    # Inject our button after the ES stop button (last position in the menu)
    new_content = content.replace(
        es_stop_end,
        es_stop_end + addon_start + kill_button_code + addon_end
    )

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

  /* --- Now Playing: replace ghost icon zone with current music --- */
  var npPoll=null,npLastTrack="",npLastFilepath="",npLastBytePos=0,npContainer=null,npFailCount=0,npMaxFails=10;
  var npAudioEl=null,npAudioPlaying=false,npAudioTrack="",npContinuous=true,npWasPlaying=false;
  var npStyle=document.createElement("style");
  npStyle.textContent=
    ".wma-now-playing{display:flex;flex-direction:column;align-items:center;justify-content:center;"+
    "gap:12px;padding:24px;text-align:center;height:100%;min-height:180px;animation:wma-np-fadein .5s ease}"+
    ".wma-now-playing .wma-np-icon{font-size:3.5rem;color:#00d4ff;animation:wma-np-pulse 2s ease-in-out infinite}"+
    ".wma-now-playing .wma-np-label{font-size:.85rem;text-transform:uppercase;letter-spacing:2px;opacity:.5}"+
".wma-now-playing .wma-np-track{font-size:1.5rem;font-weight:600;line-height:1.3;word-break:break-word}"+
".wma-now-playing .wma-np-system{font-size:.85rem;opacity:.6;font-style:italic}"+
    ".wma-now-playing .wma-np-cover{display:block;height:180px;width:auto;max-width:100%;border-radius:8px;object-fit:contain;"+
    "box-shadow:0 4px 16px rgba(0,0,0,.4);opacity:0;transition:opacity .5s ease}"+
    ".wma-now-playing .wma-np-cover.loaded{opacity:1}"+
    ".wma-np-buttons{display:flex;gap:12px;align-items:center;justify-content:center;margin-top:4px}"+
    ".wma-now-playing .wma-np-playbtn,.wma-now-playing .wma-np-autobtn{background:rgba(0,212,255,.25);border:2px solid #00d4ff;"+
    "color:#fff;font-size:1.2rem;width:40px;height:40px;border-radius:50%;"+
    "cursor:pointer;display:flex;align-items:center;justify-content:center;"+
    "transition:all .2s ease}"+
    ".wma-now-playing .wma-np-playbtn:hover,.wma-now-playing .wma-np-autobtn:hover{background:rgba(0,212,255,.5);border-color:#0af}"+
    ".wma-now-playing .wma-np-autobtn{opacity:.35;font-size:1rem}"+
    ".wma-now-playing .wma-np-autobtn.active{opacity:1}"+
    ".overlayMessage.wma-has-player{padding:0;display:flex;align-items:center;justify-content:center}"+
    "@keyframes wma-np-pulse{0%,100%{opacity:1}50%{opacity:.4}}"+
    "@keyframes wma-np-fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}";
  document.head.appendChild(npStyle);

  var npLoadingMsgs={fr:"Chargement de la musique\\u2026",en:"Loading music\\u2026"};
  var npNowPlayingMsgs={fr:"En cours de lecture",en:"Now Playing"};

  function showLoading(overlay){
    var lang=getLang();
    var div=document.createElement("div");
    div.className="wma-now-playing";
    div.innerHTML=
      "<div class=\\"wma-np-icon\\" style=\\"animation:wma-np-pulse 1s ease-in-out infinite\\">\\u266b</div>"+
      "<div class=\\"wma-np-label\\">"+(npLoadingMsgs[lang]||npLoadingMsgs.en)+"</div>";
    overlay.innerHTML="";
    overlay.appendChild(div);
    overlay.classList.remove("server-off","sleep-mode");
    overlay.style.background="none";
    overlay.classList.add("wma-has-player");
    npContainer=div;
  }

  /* Replace ghost immediately when it appears */
  new MutationObserver(function(mutations,obs){
    var ghost=document.querySelector(".sleep-mode .mdi-ghost-off-outline");
    if(ghost&&(!npContainer||!npContainer.isConnected)){
      npContainer=null;
      npLastTrack="";
      var overlay=ghost.closest(".overlayMessage");
      if(overlay) showLoading(overlay);
    }
    if(!ghost){
      /* Not in sleep mode — check if npContainer got detached (wake from sleep) */
      var anyGhost=document.querySelector(".mdi-ghost-off-outline");
      if(anyGhost&&npContainer&&!npContainer.isConnected){
        npContainer=null;npLastTrack="";
        var overlay=anyGhost.closest(".overlayMessage");
        if(overlay) showLoading(overlay);
      }
    }
  }).observe(document.body,{childList:true,subtree:true});

  function parseTrack(name){
    /* Extract [SYSTEM] and track name from format: "\\u266a [SNES] Game - Track" */
    var r={system:"",title:name||"",game:""};
    if(!name)return r;
    /* Remove leading music note */
    var s=name.replace(/^\\u266a\\s*/,"");
    var m=s.match(/^\\[([^\\]]+)\\]\\s*(.*)$/);
    if(m){r.system=m[1];r.title=m[2]}
    else{r.title=s}
    /* Extract game name (before first " - ") */
    var dash=r.title.indexOf(" - ");
    r.game=dash>0?r.title.substring(0,dash):r.title;
    return r;
  }

  function updateNowPlaying(){
    /* Only act when we are on the home page and no game is running */
    var ghost=document.querySelector(".sleep-mode .mdi-ghost-off-outline");
    var overlay=null;
    if(ghost){
      overlay=ghost.closest(".overlayMessage");
    }else if(npContainer&&npContainer.parentNode){
      /* Already replaced: use the parent overlay */
      overlay=npContainer.parentNode.closest(".overlayMessage")||npContainer.parentNode;
    }else{
      /* npContainer is stale (detached after sleep wake) — reset and find home overlay */
      npContainer=null;npLastTrack="";
      var anyGhost=document.querySelector(".mdi-ghost-off-outline");
      if(anyGhost) overlay=anyGhost.closest(".overlayMessage");
    }
    if(!overlay)return;

    fetch(API+"/api/now-playing").then(function(r){return r.json()}).then(function(d){
      if(!d.playing){
        npFailCount++;
        /* After repeated failures, show "no music" message */
        if(npFailCount>=npMaxFails){
          var lang=getLang();
          var noMusicMsg={fr:"Aucune musique d\\u00e9tect\\u00e9e",en:"No music detected"};
          var div=document.createElement("div");
          div.className="wma-now-playing";
          div.innerHTML=
            "<div class=\\"wma-np-icon\\" style=\\"animation:none;opacity:.3\\">\\u266b</div>"+
            "<div class=\\"wma-np-track\\" style=\\"opacity:.4\\">"+(noMusicMsg[lang]||noMusicMsg.en)+"</div>";
          if(npContainer&&npContainer.parentNode){
            npContainer.parentNode.replaceChild(div,npContainer);
          }else if(overlay){
            overlay.innerHTML="";
            overlay.appendChild(div);
            overlay.classList.remove("server-off","sleep-mode");
            overlay.style.background="none";
          }
          npContainer=div;npLastTrack="";
        }
        return;
      }
      npFailCount=0;
      if(d.track===npLastTrack&&npContainer)return;
      var isWakeRecovery=!npLastTrack;
      npLastTrack=d.track||"";
      npLastFilepath=d.filepath||"";
      npLastBytePos=d.byte_pos||0;
      var wasAuto=npWasPlaying&&(npContinuous||isWakeRecovery);
      /* Stop old audio when track changes (unless auto-play, re-start below) */
      if(npAudioEl&&!npAudioEl.paused){npAudioEl.pause();npAudioEl.src="";npAudioPlaying=false}
      var info=parseTrack(d.track);
      var div=document.createElement("div");
      div.className="wma-now-playing";
      div.innerHTML=
        "<div class=\\"wma-np-icon\\">\\u266b</div>"+
        "<div class=\\"wma-np-label\\">"+(npNowPlayingMsgs[getLang()]||npNowPlayingMsgs.en)+"</div>"+
        "<div class=\\"wma-np-track\\">"+escHtml(info.title)+"</div>"+
        (info.system?"<div class=\\"wma-np-system\\">"+escHtml(info.system)+"</div>":"")+
        "<div class=\\"wma-np-buttons\\">"+
        "<button class=\\"wma-np-playbtn\\" title=\\"Play/Stop\\">\\u25b6</button>"+
        "<button class=\\"wma-np-autobtn\\" title=\\"Auto-play\\"><i class=\\"q-icon notranslate mdi mdi-autorenew\\" aria-hidden=\\"true\\" role=\\"img\\"></i></button>"+
        "</div>"+
        "";
      /* Replace the overlay content */
      if(npContainer&&npContainer.parentNode){
        npContainer.parentNode.replaceChild(div,npContainer);
      }else{
        overlay.innerHTML="";
        overlay.appendChild(div);
      }
      overlay.classList.remove("server-off","sleep-mode");
      overlay.style.background="none";
      npContainer=div;
      /* Lazy-load cover art */
      if(info.game){
        fetchCover(info.game,info.system,npLastTrack);
      }
      /* Attach play button handler */
      var playBtn=npContainer.querySelector(".wma-np-playbtn");
      if(playBtn)playBtn.onclick=function(){npTogglePlay(this)};
      /* Attach auto-play toggle handler */
      var autoBtn=npContainer.querySelector(".wma-np-autobtn");
      if(autoBtn){
        if(npContinuous)autoBtn.classList.add("active");
        autoBtn.onclick=function(){
          npContinuous=!npContinuous;
          this.classList.toggle("active");
        };
      }
      /* Auto-play new track if continuous mode was active */
      if(wasAuto&&playBtn)npTogglePlay(playBtn);
    }).catch(function(){});
  }

  function setCover(url){
    var np=document.querySelector(".wma-now-playing");
    if(!np)return;
    var old=document.getElementById("wma-np-cover-img");
    if(old)old.remove();
    var img=document.createElement("img");
    img.className="wma-np-cover";
    img.id="wma-np-cover-img";
    img.alt="";
    img.onload=function(){
      img.classList.add("loaded");
      var ic=np.querySelector(".wma-np-icon");
      if(ic)ic.style.display="none";
    };
    img.onerror=function(){img.remove()};
    img.src=url;
    np.insertBefore(img,np.firstChild);
  }
  function fetchCover(gameName,system,trackSnapshot){
    var norm=gameName.replace(/^(.+),\s*(the)\s*$/i,"The $1");
    var gn=norm.toLowerCase().replace(/[^a-z0-9]/g,"");
    var lang=getLang();
    var domain=lang==="fr"?"fr":"en";
    var idx=0;
    function makeUrl(d){
      var suffix=d==="en"?" "+system+" video game":" "+system;
      return "https://"+d+".wikipedia.org/w/api.php?action=query&list=search&srsearch="
        +encodeURIComponent(norm+suffix)+"&format=json&origin=*&srlimit=5";
    }
    function titleMatch(dt){
      var min=Math.min(gn.length,dt.length);
      var pref=0;while(pref<min&&gn[pref]===dt[pref])pref++;
      var suff=0;while(suff<min&&gn[gn.length-1-suff]===dt[dt.length-1-suff])suff++;
      return (pref+suff)>=Math.min(gn.length,dt.length)*0.7;
    }
    function searchDomain(d){
      var url=makeUrl(d);
      console.log("cover search:",url);
      fetch(url).then(function(r){return r.json()})
      .then(function(data){
        var res=data.query&&data.query.search||[];
        tryResult(res);
      }).catch(function(){});
    }
    function fetchPageImage(pageTitle,results){
      var listUrl="https://"+domain+".wikipedia.org/w/api.php?action=query&titles="
        +encodeURIComponent(pageTitle)+"&prop=images&format=json&origin=*";
      fetch(listUrl).then(function(r){return r.json()})
      .then(function(d){
        var images=[];
        for(var pid in d.query&&d.query.pages||{}){
          if(d.query.pages[pid].images)images=d.query.pages[pid].images;
        }
        if(!images.length){tryResult(results);return;}
        var c=null;
        for(var i=0;i<images.length;i++){
          var n=images[i].title.toLowerCase();
          if((!c||n.match(/(logo|cover|pochette|flyer|jaquette)/))&&!n.match(/\.(svg|pdf)$/))
            c=images[i];
        }
        if(!c)c=images[0];
        var imgUrl="https://"+domain+".wikipedia.org/w/api.php?action=query&titles="
          +encodeURIComponent(c.title)+"&prop=imageinfo&iiprop=url&format=json&origin=*";
        fetch(imgUrl).then(function(r){return r.json()})
        .then(function(id){
          for(var pid in id.query&&id.query.pages||{}){
            var info=id.query.pages[pid].imageinfo;
            if(info&&info[0]&&info[0].url){setCover(info[0].url);return}
          }
          tryResult(results);
        }).catch(function(){tryResult(results)});
      }).catch(function(){tryResult(results)});
    }
    function tryResult(results){
      if(!results||idx>=results.length){
        if(domain!=="en"){domain="en";idx=0;searchDomain(domain)}
        return;
      }
      var title=results[idx++].title;
      fetch("https://"+domain+".wikipedia.org/api/rest_v1/page/summary/"+encodeURIComponent(title))
      .then(function(r){if(r.ok)return r.json();throw r.status})
      .then(function(d){
        if(npLastTrack!==trackSnapshot)return;
        var dt=d.title.toLowerCase().replace(/[^a-z0-9]/g,"");
        if(d.thumbnail&&d.thumbnail.source&&d.type!="disambiguation"&&titleMatch(dt))
          setCover(d.thumbnail.source);
        else if(titleMatch(dt)&&d.type!="disambiguation")
          fetchPageImage(title,results);
        else tryResult(results);
      }).catch(function(){tryResult(results)});
    }
    searchDomain(domain);
  }

  function createGhost(){
    var el=document.createElement("i");
    el.className="q-icon notranslate mdi mdi-ghost-off-outline";
    el.setAttribute("aria-hidden","true");el.setAttribute("role","img");
    return el;
  }
  function escHtml(s){
    var d=document.createElement("div");d.textContent=s;return d.innerHTML;
  }
  function npTogglePlay(btn){
    if(npAudioEl&&!npAudioEl.paused){
      npAudioEl.pause();
      npAudioEl.src="";
      npAudioPlaying=false;npWasPlaying=false;
      if(btn)btn.textContent="\\u25b6";
      return;
    }
    if(!npLastFilepath){
      console.warn("[webmanager-addon] No track filepath cached");
      return;
    }
    npAudioTrack=npLastTrack;
    var streamUrl=API+"/api/audio/stream?path="+encodeURIComponent(npLastFilepath)+"&t="+Date.now();
    if(!npAudioEl){
      npAudioEl=document.createElement("audio");
      npAudioEl.crossOrigin="anonymous";
      npAudioEl.style.display="none";
      document.body.appendChild(npAudioEl);
      npAudioEl.onended=function(){
        npAudioPlaying=false;
        npAudioEl.src="";
        var b=document.querySelector(".wma-np-playbtn");
        if(b)b.textContent="\\u25b6";
      };
    }
    npAudioEl.src=streamUrl;
    npAudioEl.play().then(function(){
      npAudioPlaying=true;npWasPlaying=true;
      if(btn)btn.textContent="\\u23f9";
    }).catch(function(e){
      console.warn("[webmanager-addon] Audio play failed:",e);
    });
  }

  /* Poll every 10s for now-playing */
  npPoll=setInterval(updateNowPlaying,10000);
  /* Initial check after 1.5s */
  setTimeout(updateNowPlaying,1500);
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
