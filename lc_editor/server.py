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
    "media_proxy",
    "media_analyze",
    "shots_list",
    "shots_search",
    "shots_rank",
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
    "layout_list",
    "layout_add",
    "layout_update",
    "layout_pane",
    "layout_clear",
    "motion_kenburns",
    "motion_punch",
    "motion_zoom_in",
    "motion_zoom_out",
    "motion_none",
    "motion_hold",
    "motion_speed",
    "transition_set",
    "transition_audio_xfade",
    "fx_grain",
    "fx_vignette",
    "fx_wrap",
    "caption_add",
    "caption_edit",
    "caption_move",
    "caption_remove",
    "caption_lint",
    "sfx_list",
    "sfx_place",
    "sfx_caption_auto",
    "sfx_transition_auto",
    "sfx_zoom_auto",
    "audio_bed",
    "audio_duck",
    "audio_highpass",
    "audio_denoise",
    "audio_gate",
    "mix_preview",
    "grade_set",
    "grade_preset",
    "grade_protect",
    "adjustment_set",
    "adjustment_clear",
    "overlay_preview",
    "overlay_bake",
    "preview_stills",
    "preview_proxy",
    "preview_clip",
    "review_report",
    "export",
    "layer_add",
    "layer_update",
    "layer_remove",
    "layer_reorder",
    "layer_transform",
    "layer_keyframe",
    "effect_add",
    "effect_update",
    "effect_remove",
    "text_style",
    "template_list",
    "template_apply",
    "template_save",
    "music_add",
    "music_update",
    "music_remove",
    "music_list",
    "beat_analyze",
    "beat_edit",
    "beat_sync_preview",
    "beat_sync_apply",
    "undo",
    "redo",
]


def build_mcp(editor: Editor):
    try:
        from mcp.server import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server

    mcp = Server("lc-editor")
    for name in TOOLS:
        fn = getattr(editor, name)
        mcp.tool(name=name)(fn)
    return mcp


def run_stdio(editor: Editor) -> None:
    mcp = build_mcp(editor)
    mcp.run()
