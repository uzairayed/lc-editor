# lc-editor

A local video editor you drive from an MCP client. There is no timeline UI to click. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels. No music. Captions are stroke-and-shadow text, never a box. The rules that reject bad edits live in `specs/` and `instructions.md`.

## Needs

- Python 3.12 or newer
- ffmpeg and ffprobe on your PATH

## Install

From a clone of this repo:

```
pipx install .
```

`pip install .` works too. pipx keeps the app in its own env and puts `lc-editor` on your PATH.

## Run

```
lc-editor serve --project ./my-reel
```

MCP is stdio. Point Cursor (or another MCP client) at that command.

`--web` starts a page on 127.0.0.1:8765 that can show stills. It only reads. It cannot change the cut.

## Tools

Session, media, edit, captions, sound, grade, preview, export. Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud (music, a caption box, a hold that is too short). They are not quietly "fixed."

Same `op_id` twice does not add the clip twice. Export will not run until `review_report` has been called on the current timeline.

## Not in this version

Multicam, speech-to-captions, stock music, beat sync, a pile of transitions, or a browser you edit in.
