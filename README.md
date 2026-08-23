# lc-editor

A local video editor for a computer use agent, made for grokbot. You drive it from an MCP client; there is no timeline UI to click. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels. Captions are stroke-and-shadow text, never a box. Sound is the owner's call, not the editor's; the agent should ask before assuming. This version only renders natural audio (engine, wind, ambience, short SFX), music tracks are not supported yet. Engine rules live in `specs/craft.md`. Karachi episode structure is an optional preset, not the default.

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

Optional: `project_create(..., preset="karachi")` loads series branding. Other reels do not need it.

## Giving this to grokbot

Once the MCP server is in grokbot's config, hand it a prompt like this:

```
You have an MCP server called lc-editor. It is a video editor you control
entirely through tool calls; ffmpeg does the rendering.

My raw clips are in <folder>. Cut a 9:16 reel of <subject>, 15 to 28 seconds.
Follow the craft rules in specs/craft.md: stroke-and-shadow captions with no
background box, hard cuts on motion.

Before you touch the timeline, ask me what I want for sound: music or natural
audio only. Do not assume either way. If I ask for music, tell me this version
of the editor cannot render it yet and offer natural audio plus SFX instead.

Work in passes: analyze the footage first, pick the strongest shots, build the
timeline, then run review_report and fix every warning before you export.
Show me preview stills at each pass before moving on.
```

Swap the folder, subject, and any series preset (for example `preset="karachi"`) into the prompt as needed.

## Not in this version

Multicam, speech-to-captions, stock music, beat sync, Drive import, or a browser you edit in.
