# lc-editor

A local video editor for a computer use agent, made for grokbot. You drive the cut from an MCP client; there is no timeline UI to click. `lc-editor serve --web` opens a localhost desk for previewing and labeling clips. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels and SDR YouTube upload masters. `project_create(preset="youtube")` defaults to 1920×1080 and `export(preset="youtube")` writes a verified H.264/AAC `youtube.mp4` plus upload metadata and optional SRT captions. Captions are stroke-and-shadow text, never a box. Sound is the owner's call, not the editor's: ask before assuming music or natural audio. This version composites multiple layers, applies a small effect pack, expands templates into ordinary timeline items, and can mix owner-imported music with beat sync. Engine rules live in `specs/craft.md`. Karachi episode structure is an optional preset, not the default.

## Needs

- Python 3.11 or newer
- ffmpeg and ffprobe on your PATH

## Install

From a clone of this repo:

```
pipx install .
```

`pip install .` works too. pipx keeps the app in its own env and puts `lc-editor` on your PATH.

From GitHub:

```
pipx install git+https://github.com/uzairayed/lc-editor.git
```

## Run

```
lc-editor serve --project ./my-reel
```

`--project` defaults to `./reel` if omitted. `--web` starts the labeling desk on 127.0.0.1:8765. Label writes go through the same MCP tools; the page does not edit the timeline.

```
lc-editor version
lc-editor doctor
lc-editor doctor --project /absolute/path/to/project
```

`version` prints the package version. `doctor` checks Python 3.11+, the resolved `lc-editor` binary on PATH, ffmpeg and ffprobe, the MCP tool count from `TOOLS`, and that `project_create` / `import_file` / `import_folder` / `clip_add` / `export` exist. It always prints copy-paste Grok Bot / Cursor MCP JSON (`command` + `args` + `env`). Optional `--project` is a dry smoke: it reports whether the project exists or can be created. It does not encode or export. This is the attach path for #29 / #32.

## Cursor Marketplace Plugin

This repo is packaged as a Cursor Agent Plugin. Install the `lc-editor` plugin from the Cursor Marketplace. `mcp.json` pins **command** `lc-editor` and **args** `["serve"]` so a `pip install -U` does not drop the connector.

**Requirements:** ffmpeg, ffprobe, Python 3.11+, and `lc-editor` on your PATH (`pipx install .` or `pip install .`). After `pip install -U lc-editor`, restart MCP: Cursor **RestartMcpServers**, or start a new agent session. Grok Bot: re-attach with the JSON from `lc-editor doctor`. There is no RestartMcpServers CLI.

The plugin includes:
- `plugin.json` — Agent Plugins manifest
- `mcp.json` — MCP server configuration (stdio; PATH-pinned `lc-editor serve`)
- `skills/lc-editor/SKILL.md` — guidance for agents on when/how to use the editor

## Attach MCP (Grok Bot / Cursor / any stdio client)

The editor is not a CLI of edit commands. Agents call MCP tools (`project_create`, `import_folder`, `clip_add`, `export`, …). Those tools appear only after you attach `lc-editor serve` as an MCP server.

One-liner attach (stdio):

- **command:** `lc-editor`
- **args:** `serve --project <absolute path>`

Cursor / Grok Bot `mcp.json` (or Cursor MCP settings):

```json
{
  "mcpServers": {
    "lc-editor": {
      "command": "lc-editor",
      "args": ["serve", "--project", "/absolute/path/to/project"]
    }
  }
}
```

Restart the agent session after changing MCP config. Then confirm `project_create` is a callable tool. If it is not in the tool catalog, the session is not attached — run `lc-editor doctor` and paste the JSON it prints. Do not fall back to raw ffmpeg while doctor is green.

### Persist across upgrades (#29 / #32)

MCP attach is client-side. `pip install -U lc-editor` does not re-register the server. Pin `command` to the installed binary (`lc-editor doctor` prints `lc_editor_bin`) and `args` to `["serve"]`:

```json
{
  "command": "/absolute/path/to/lc-editor",
  "args": ["serve"],
  "env": {}
}
```

Cursor `mcp.json` (same pin; marketplace plugin ships this):

```json
{
  "mcpServers": {
    "lc-editor": {
      "command": "lc-editor",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

Then restart MCP so a fresh session can call `project_create` without rediscovering AddMcpServer:

1. Cursor: **RestartMcpServers** (or a new agent session).
2. Grok Bot: re-attach (`AddMcpServer` with the doctor JSON). There is no `RestartMcpServers` CLI.

If `lc-editor` is missing from PATH, doctor still prints JSON with `command: lc-editor` and warns that tools will be invisible until PATH / AddMcpServer is fixed.

### Windows paths

Use an **absolute** project path.

- Forward slashes work in JSON: `C:/Users/you/my-reel`
- Backslashes must be escaped: `C:\\Users\\you\\my-reel`
- After `pipx install .`, confirm the binary: PowerShell `Get-Command lc-editor`, cmd `where lc-editor`
- If `lc-editor` is not on PATH, set `command` to the full exe path (pipx usually puts it under `%USERPROFILE%\\.local\\bin\\lc-editor.exe`)

### Verify tools appeared

1. `lc-editor doctor` — `mcp_tools` should be ~100, `lc_editor_bin` should be a path, and `project_create` / `import_*` / `clip_add` / `export` should read `ok`. Copy the MCP JSON it prints.
2. `lc-editor doctor --project C:/Users/you/my-reel` — reports exists or can create. No encode.
3. In the agent session, `project_create` is callable. If MCP tools are missing, paste doctor's JSON, **RestartMcpServers** (Cursor) or re-attach (Grok Bot), and re-run doctor. Stay off ffmpeg until doctor is red.

You can also use `uvx` to run without installing first:

```json
{
  "mcpServers": {
    "lc-editor": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/uzairayed/lc-editor.git", "lc-editor", "serve"]
    }
  }
}
```

## Cursor (manual MCP config)

If you prefer manual configuration instead of the marketplace plugin, use the attach snippet above (or the JSON from `lc-editor doctor`). The marketplace plugin ships the same PATH-pinned stdio server via `mcp.json`.

## Tools

Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud. Same `op_id` twice does not duplicate. `review_report` must pass before `export`. Preview stills and the contact sheet are JPEG files on disk, not base64.

The primary track is still the gapless `clips` list (`clip_add`, trim, split, reorder, motion, transitions). `motion_zoom_in` / `motion_zoom_out` are a 12-frame scale hit (not Ken Burns). Two or more sources can share one slot (`layout_add`). Overlays, look, and music sit beside it:

- Layers: `layer_add` / `layer_update` / `layer_remove` / `layer_reorder` / `layer_transform` / `layer_keyframe` for timed video, image, or text. `text_style` sets fade, pop, slide, or type-on. `effect_add` / `effect_update` / `effect_remove` attach `blur`, `sharpen`, `glow`, `grain`, `vignette`, `lut`, or `color`. Raw ffmpeg filter strings are rejected.
- Templates: `template_list`, `template_apply("editorial"|"karachi", bindings=...)`, `template_save`. Apply writes ordinary layers and look; the project stays editable.
- Music: default is off. `project_set(allow_music=true)` is the owner opt-in. Then `import_file` a local `.mp3`/`.wav`/`.m4a` and `music_add`. `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply`. There is no stock catalog; licensing stays with the owner.
- Layouts: `layout_add("stack_v"|"stack_h"|"stack_v3"|"grid_2x2", panes=[...])` composites two to four sources into one clip. `layout_pane` refocuses a cell. `layout_clear` flattens back to pane 0. A vista or reveal stays full-frame.
- Captions: `caption_add` still works and syncs to a bound text layer. No box, banner, or scrim. Process / product reels use `style="card"` (Clash Display via `font="clash"`). `pop` / `karaoke` are spoken-word only.
- Album cards: `media_card_propose` / `media_card_confirm` lock day, role, and what's in frame before story lock. Shot overrides use `shot_card_confirm`. `label_queue` / `label_get` / `label_readiness` are the same contract the localhost labeling desk (`lc-editor serve --web`) uses. `shoot_day_suggest` clusters capture times. Folder names (`before/`, `day1`) tag untagged imports. `review_report` warns on inverted before/after capture order and uncarded bookend slots.

Optional: `project_create(..., preset="karachi")` loads series branding. Other reels do not need it.

## Capability matrix

| Area | In this version |
| --- | --- |
| Canvas | 1080x1920, 30fps, MCP only |
| Primary track | Gapless clips, trim/split/reorder, kenburns/punch/zoom_in/zoom_out |
| Layouts | `stack_v`, `stack_h`, `stack_v3`, `grid_2x2`. One timeline slot |
| Layers | Timed video, image, and text overlays with z-order, transform, keyframes |
| Effects | Registry: blur, sharpen, glow, grain, vignette, lut, color |
| Text | Stroke-and-shadow only. Motion: fade, pop, slide, type-on |
| Templates | `editorial`, `karachi`; apply expands to ordinary layers |
| Sound | Natural audio, beds, SFX (ride kinds plus reel `sparkle`/`swipe`/`bubble`/`button`/`paper`/`cash`/`click`/`correct`/`success`). Agent pack: `sfx_pack_add` checkout `packs/reel-sfx` (Mixkit License). Extra owner imports via `sfx_import` / `sfx_pack_add` into project `user-sfx/` (license `CC0` / `Mixkit` / `Pixabay`; Mixkit / Pixabay / Freesound; never CapCut). Music is opt-in via `project_set(allow_music=true)` then `music_add` |
| Beat sync | `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply` |
| Look | One adjustment layer (LUT, grain, vignette) after the cut |
| Album cards | Propose / confirm per-media day + role + subjects. Capture-order guard. Folder-name hints |

## Giving this to grokbot

Once the MCP server is in grokbot's config, hand it a prompt like this:

```
You have an MCP server called lc-editor. It is a video editor you control
entirely through tool calls; ffmpeg does the rendering.

My raw clips are in <folder>. Cut a 9:16 reel of <subject>, 15 to 28 seconds.
Follow the craft rules in specs/craft.md: stroke-and-shadow captions with no
background box, hard cuts on motion.

Before you touch the timeline, ask me what I want for sound: music or natural
audio only. Do not assume either way. If I ask for music, call
project_set(allow_music=true), import my track, music_add it, beat_analyze,
show me beat_sync_preview, then beat_sync_apply only after I confirm.

Work in passes: analyze the footage first, pick the strongest shots, then
match what you see in the keyframes to context/INDEX.md and read only those
scene cards (process in context/HOW.md) before you set durations or roles.
Build the timeline. An occasional two-up is context/scenes/pair.md.
A reel that is mostly stacks is collage.md. Two ride POVs is
ride-pair.md. Add layers or a template if needed, then run
review_report and fix every warning before you export. Show me
preview stills at each pass.
```

Swap the folder, subject, and any series preset (for example `preset="karachi"`) into the prompt as needed.

Scene holds (door as a reveal, tile as a detail, highway as punctuation) live in `context/`. The agent looks up subjects in `context/INDEX.md` and reads only the matching cards. That library is editorial judgment. Engine floors in `specs/craft.md` still win when they conflict.

## Not in this version

Multicam, speech-to-captions, a stock music catalog, Drive import, or a browser you edit in.

## Submitting to the Cursor Marketplace

To publish this plugin to the Cursor Marketplace or Cursor Directory:

1. **Cursor Marketplace:** Go to https://cursor.com/marketplace/publish, sign in, and submit the plugin using this repo's URL.

2. **Cursor Directory:** Go to https://cursor.directory/plugins/new and follow the submission steps.

Once published, Grok Bot templates and other agents can reference this plugin by its marketplace ID.
