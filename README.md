# lc-editor

A local video editor for a computer use agent, made for grokbot. You drive it from an MCP client; there is no timeline UI to click. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels (1080x1920, 30fps). Captions are stroke-and-shadow text, never a box. Sound is the owner's call, not the editor's: ask before assuming music or natural audio. This version composites multiple layers, applies a small effect pack, expands templates into ordinary timeline items, and can mix owner-imported music with beat sync. Engine rules live in `specs/craft.md`. Karachi episode structure is an optional preset, not the default.

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

`--web` starts a page on 127.0.0.1:8765 that can show stills. It only reads.

## Cursor

Add this to your MCP config. Use an absolute project path.

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

On Windows the path looks like `C:/Users/you/my-reel`.

## Tools

Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud. Same `op_id` twice does not duplicate. `review_report` must pass before `export`. Preview stills and the contact sheet are JPEG files on disk, not base64.

The primary track is still the gapless `clips` list (`clip_add`, trim, split, reorder, motion, transitions). Two or more sources can share one slot (`layout_add`). Overlays, look, and music sit beside it:

- Layers: `layer_add` / `layer_update` / `layer_remove` / `layer_reorder` / `layer_transform` / `layer_keyframe` for timed video, image, or text. `text_style` sets fade, pop, slide, or type-on. `effect_add` / `effect_update` / `effect_remove` attach `blur`, `sharpen`, `glow`, `grain`, `vignette`, `lut`, or `color`. Raw ffmpeg filter strings are rejected.
- Templates: `template_list`, `template_apply("editorial"|"karachi", bindings=...)`, `template_save`. Apply writes ordinary layers and look; the project stays editable.
- Music: default is off. `project_set(allow_music=true)` is the owner opt-in. Then `import_file` a local `.mp3`/`.wav`/`.m4a` and `music_add`. `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply`. There is no stock catalog; licensing stays with the owner.
- Layouts: `layout_add("stack_v"|"stack_h"|"stack_v3"|"grid_2x2", panes=[...])` composites two to four sources into one clip. `layout_pane` refocuses a cell. `layout_clear` flattens back to pane 0. A vista or reveal stays full-frame.
- Captions: `caption_add` still works and syncs to a bound text layer. No box, banner, or scrim.

Optional: `project_create(..., preset="karachi")` loads series branding. Other reels do not need it.

## Capability matrix

| Area | In this version |
| --- | --- |
| Canvas | 1080x1920, 30fps, MCP only |
| Primary track | Gapless clips, trim/split/reorder, kenburns/punch |
| Layouts | `stack_v`, `stack_h`, `stack_v3`, `grid_2x2`. One timeline slot |
| Layers | Timed video, image, and text overlays with z-order, transform, keyframes |
| Effects | Registry: blur, sharpen, glow, grain, vignette, lut, color |
| Text | Stroke-and-shadow only. Motion: fade, pop, slide, type-on |
| Templates | `editorial`, `karachi`; apply expands to ordinary layers |
| Sound | Natural audio, beds, SFX. Music is opt-in via `project_set(allow_music=true)` then `music_add` |
| Beat sync | `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply` |
| Look | One adjustment layer (LUT, grain, vignette) after the cut |

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
