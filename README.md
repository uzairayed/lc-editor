# lc-editor

A local video editor you drive from an MCP client. There is no timeline UI to click. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels. No music. Captions are stroke-and-shadow text, never a box. Engine rules live in `specs/craft.md`. Karachi episode structure is an optional preset, not the default.

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

Optional: `project_create(..., preset="karachi")` loads series branding. A Murree cut does not need it.

## Unexpected Murree

Point `LC_EDITOR_MURREE_DIR` at a folder of exactly 117 stills on this machine, then:

```
$env:LC_EDITOR_MURREE_DIR="C:\path\to\murree"
pytest -m murree -s
```

Unix:

```
LC_EDITOR_MURREE_DIR=/path/to/murree pytest -m murree -s
```

The stills stay local. They are not in this repo.

## Not in this version

Multicam, speech-to-captions, stock music, beat sync, Drive import, or a browser you edit in.
