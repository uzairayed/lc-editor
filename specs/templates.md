# SPEC-TPL: Templates

Source: Production Reel Foundation v2.

## SPEC-TPL-01: files

Templates live under `lc_editor/presets/` as versioned JSON (`schema_version: 2`). Shipped: `karachi` (series branding) and `editorial` (neutral look, hook/body text placeholders).

## SPEC-TPL-02: apply expands

`template_apply(name, bindings?)` writes ordinary timeline layers, text styles, transitions, and adjustment values. After apply, `template_id` is stored. Later edits do not need the template file.

## SPEC-TPL-03: save

`template_save(name)` writes the current layers, text styles, adjustment, and placeholders into the project `templates/` folder (not the package). Name must be a simple slug.

## SPEC-TPL-04: constraints

A template cannot set `allow_music`, add a caption box, or add a banned transition. Missing required bindings become warnings, not silent defaults that invent copy.
