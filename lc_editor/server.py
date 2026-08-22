from __future__ import annotations

from lc_editor.app import Editor

TOOLS = [
    "project_create",
    "project_open",
    "project_get",
    "project_set",
    "project_list",
    "import_file",
    "import_folder",
    "media_list",
    "media_remove",
    "probe",
    "thumbnail",
    "contact_sheet",
    "proxy_build",
    "timeline_get",
    "timeline_reset",
    "clip_add",
    "clip_remove",
    "clip_reorder",
    "clip_trim",
    "clip_ripple_trim",
    "clip_split",
    "clip_set_duration",
    "clip_fit",
    "clip_refocus",
    "clip_gain",
    "clip_mute",
    "motion_kenburns",
    "motion_punch",
    "motion_none",
    "transition_set",
    "caption_add",
    "caption_edit",
    "caption_move",
    "caption_remove",
    "caption_lint",
    "sfx_list",
    "sfx_place",
    "sfx_caption_auto",
    "sfx_transition_auto",
    "audio_bed",
    "audio_duck",
    "audio_highpass",
    "mix_preview",
    "grade_set",
    "grade_preset",
    "grade_protect",
    "overlay_preview",
    "overlay_bake",
    "preview_stills",
    "preview_proxy",
    "preview_clip",
    "review_report",
    "export",
    "undo",
    "redo",
]


def build_mcp(editor: Editor):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("lc-editor")

    def bind(name: str):
        fn = getattr(editor, name)

        def tool(**kwargs):
            return fn(**kwargs)

        tool.__name__ = name
        tool.__doc__ = fn.__doc__ or name
        return mcp.tool(name=name)(tool)

    for name in TOOLS:
        bind(name)
    return mcp


def run_stdio(editor: Editor) -> None:
    mcp = build_mcp(editor)
    mcp.run()
