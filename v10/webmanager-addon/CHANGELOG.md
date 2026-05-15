# Changelog

## v2.3 — Auto-play, multi-language Wikipedia, page image fallback
- Auto-play toggle button (🔄 `mdi-autorenew`) for continuous playback through track changes
- Multi-language Wikipedia search: uses browser locale (fr/en) to choose domain
- System name included in search queries on both languages for better precision
- Page image fallback (`fetchPageImage`): when summary has no thumbnail, search page images for logo/cover
- Cover search URL logged to browser console for debugging
- Updated Wikipedia article matching with length ratio check

## v2.2 — Audio streaming, progressive cover search, CORS fixes
- Play/stop button on now-playing display to stream music in the browser
- CORS/ORB fixes for cross-origin audio requests
- Progressive cover art name reduction + fuzzy title matching
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

## v2.0 — Now Playing Music
- Detect and display currently playing background music track
- Cover art fetched from Wikipedia REST API
- Loading state and "no music detection" fallback
- English/French i18n support
- New API endpoint: `/api/now-playing`

## v1.0 — Initial release
- Micro HTTP API server with kill-emulator and status endpoints
- Frontend patch injecting "Kill Emulator" button in gear menu
- Mini standalone web UI on port 8081
- SIGTERM + 3s grace period + SIGKILL kill sequence
- Init.d daemon for persistence across ES restarts
