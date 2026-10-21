# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A WebUSB UF2 flasher for RP2040/RP2350 devices in BOOTSEL mode, built for SidecarTridge products. Everything is plain HTML/CSS/JS with no build step, no dependencies, no package manager, and no automated tests. It is published by GitHub Pages from the `main` branch root at https://webflash.sidecartridge.com, with Cloudflare proxying in front. The `CNAME` file sets the custom domain; do not remove it.

- `index.html` — the production page. A 4-step wizard: detect MCU, pick firmware from the catalog, grant USB access and flash, done.
- `picotoolweb.html` — a developer tool for sending raw PicoBoot commands (exclusive, exit XIP, get info, read, etc.) to a connected BOOTSEL device. Shares the same `PicoTool`/`findIface`/`withTimeout` code as the installer but is copied, not imported.
- `devices.json` — the firmware catalog, and the only copy the page reads. `DEVICES_JSON_URL` is the relative path `devices.json`, fetched from the same origin with a cache-busting `_ts` query param. The old S3 copy (`s3.eu-west-3.amazonaws.com/tosemulator.sidecartridge.com/devices.json`) was deleted on 2026-10-21; do not recreate it.
- `tools/check-devices.py` — validates `devices.json` (parses, required fields, unique ids, `device_type`, valid `datetime`, every `uf2_url` answers). Run it before every PR that touches the catalog: `python3 tools/check-devices.py` (add `--offline` to skip the URL checks).

**Naming in the catalog.** Hardware is "board revision N" ("board revision 3", "board revisions 1 and 2"), software is "firmware vX.Y.Z"; never a bare "v3" that could mean either. The Amiga product is the "Kickstart Multi ROM". Catalog `id`s keep their old spelling (`tosemulator-family-rev3`, `tos-emulator-v4-upgrade`, ...): they are identifiers, not text.

**Releasing firmware.** Only the `.uf2` binaries go to S3 (`tosemulator.sidecartridge.com`). The catalog changes here, by PR. Upload the binary first, then merge the PR that points to it, so the page never offers a file that does not exist yet.

`AGENTS.md` also holds project conventions (single file, plain JS, inline CSS, ASCII text, picotool-style ROM protocol). Keep it in sync with changes here.

## Running and testing

There is no build. Open the HTML file in a Chromium-based browser (Chrome, Edge, Brave). WebUSB is not available on Firefox/Safari, and the page hides the flashing UI and shows manual-install instructions there (`enforceBrowserSupport`, `manualOnly`).

Serve it over HTTP: the page fetches `devices.json` with a relative URL, which Chromium blocks on `file://`, so opening the file directly shows the page but no catalog.

```
python3 -m http.server 8000
```

Testing is manual only: a physical RP2040 or RP2350 in BOOTSEL mode, then verify the process log shows load, erase, write, (verify), reboot. There is nothing to lint or unit test.

## Architecture of the installer

All logic lives in one `<script>` block at the bottom of `index.html`.

**Wizard state.** Module-level `let` variables (`uf2`, `firmwareMeta`, `detectedMcu`, `grantedUsbDevice`, `bootselDetected`, `awaitingPostFlashConfirm`, ...) drive the UI. `setStepState`/`setStepHeader` move the accordion between steps and `updateFlashEnabled` recomputes button enablement from that state. `navigator.usb` `connect`/`disconnect` listeners keep the state live when a device is plugged/unplugged, including resetting back to step 1 if the granted device goes away mid-wizard. `awaitingPostFlashConfirm` suppresses that reset during the expected disconnect after reboot.

**Busy locks.** `detectingMcu`, `loadingFirmware`, and `flashingActive` mark a running process. `updateFlashEnabled` disables every control that must not run twice while they are set, handlers early-return on them, and the `connect` listener ignores devices while busy (a mid-flash connect used to reset the wizard and abort the write). Any new long-running action needs a flag here.

**Helper box.** `setHelp(HELP.<key>)` sets the `#helper` text above the progress bar. Every state transition (detect, download, grant, flash, copy, unplug, done, each failure) calls it, so new states or error paths should add a `HELP` entry. `helpForFlashError` picks Windows-specific advice when the error mentions `claimInterface`.

**MCU detection and catalog filtering.** Device identity comes from USB PID (`PICOBOOT_PID_RP2040` = 0x0003, `PICOBOOT_PID_RP2350` = 0x000F, vendor 0x2E8A). `renderFamilies`/`renderFirmwares` only show catalog entries whose `device_type` matches `detectedMcu`. The flash handler re-checks that the connected device, detected MCU, and selected firmware all agree before touching flash.

**Catalog format.** `devices.json` is `{ families: [ { id, name, description, image, firmwares: [ { id, name, description, device_type: "RP2040"|"RP2350", datetime, version, uf2_url, post_install_html } ] } ] }`. `post_install_html` is rendered after a successful flash through `sanitizeAllowedHtml`, which allows only a/b/br/em/i/li/ol/p/strong/u/ul and http(s) hrefs. Add new firmware by appending an entry with a unique `id` and the correct `device_type`.

**UF2 handling.** `parseUF2` validates magic numbers and family IDs (with `ADVANCED_UF2_VALIDATION`), yields `{ blocks, ranges }` where `ranges` are the 4 KB-sector-aligned erase ranges derived from block addresses.

**Flash sequence** (the `flashBtn` handler): open device, `findIface` (prefers the second listed interface if it is vendor-class 0xFF with bulk in/out, else scans all), then `PicoTool`: `reset` (control transfer 0x41), `exclusiveAccess(1)`, `exitXip`, optional `flashErase` per sector, `write` per block, optional verify via `read`, then `rebootToApp`. RP2350 uses `CMD_REBOOT2` (0x0A); RP2040 uses `CMD_REBOOT` with `pc=0, sp=SRAM_END`. Reboot errors that look like a disconnect are treated as success (`isExpectedDisconnectError`). `claimInterface` has a 3 s timeout and a failed `reset` is logged and skipped rather than aborting.

**Drive-copy fallback** (`flashViaDrive`, Windows only). WebUSB on Windows needs the vendor interface bound to WinUSB with a DeviceInterfaceGUID, which the RP2040 bootrom never sets up (and an RP2350 can lose through a stale driver). So on Windows, when `showDirectoryPicker` exists, step 3 also offers copying the raw `uf2Bytes` to the BOOTSEL mass-storage drive the user picks, in 64 KB chunks via the File System Access API. The bootrom reboots as soon as the last block lands, so an error on `close()` or on the final chunk counts as success. Both paths end in `showFlashSuccess`.

**Cookie banner and analytics.** The block before `</head>` is the same as `../magic-c-builder/src/consent.html`: orestbida/cookieconsent v2.9.2 (MIT) inlined verbatim, and the sidecartridge.com GA4 property `G-6VT9RXTJ2N` as a `type="text/plain" data-cookiecategory="analytics"` script, so it runs only after consent and only loads gtag on `*.sidecartridge.com`. On sidecartridge.com hosts `cookie_domain` is `sidecartridge.com`, so the `cc_cookie` choice is shared with the main site. `<body class="c_darkmode">` gives the banner its dark theme. The "Cookies" link (`data-cc="c-settings"`) at the bottom of `#app` reopens the settings.

**PicoBoot framing** (`PicoTool.runCmd`): 32-byte command packet — magic 0x431fd10b, incrementing token, cmd id, cmd size, 16-bit reserved, 32-bit transfer length, then command args. Commands with bit 7 set (e.g. read 0x84) are device-to-host and are followed by a zero-length OUT ack; others are followed by a 64-byte IN status read. Every USB transfer is wrapped in `withTimeout` so a stalled device never hangs the page.

**Progress bar phases.** `setProgressMode` toggles CSS classes `progress-load` (blue), `progress-erase` (red), `progress-write` (green), `progress-verify`. Keep these color semantics when adding phases.

---

## Working style

These behavioral guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think before coding

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first

Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical changes

Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- When your changes orphan an import/variable/function, remove it. Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

### 4. Goal-driven execution

Define success criteria. Loop until verified.
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan with a verification check per step.

### 5. No AI attribution

Never add AI-tool attribution to commits, PR descriptions, code comments,
docs, or any other artifact. This means **no**:
- "Generated with Claude Code", "Co-authored by Claude", "Made with ChatGPT",
  or any similar phrasing.
- `Co-Authored-By: Claude …`, `Co-Authored-By: ChatGPT …`, or any other
  AI co-author trailer.
- "AI-assisted", "written with the help of an LLM", etc., as comments or
  changelog entries.

Write the message as the human author. Do not mention AI tools used to
produce the work.

<!-- imported-from: codex:project:instructions -->
## Conventions (from AGENTS.md)

- Keep everything in a single HTML file when possible; plain JavaScript, no build step, inline CSS is fine.
- Favor ASCII text in edits.
- Use the Pico ROM vendor protocol (picotool-style) as the flashing path. The mass-storage drive copy exists only as the Windows driver-free fallback above; do not make it the default or extend it to other platforms without asking.
- Keep timeouts on every USB transfer. The erase step stays optional and user-controlled.
