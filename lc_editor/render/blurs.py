from __future__ import annotations

from lc_editor.models import BLUR_REF_H, ClipBlur, even_dim


def _tag(blur_id: str, index: int) -> str:
    raw = "".join(c for c in blur_id if c.isalnum()) or f"b{index}"
    return f"sb{raw}{index}"


def soft_mask_blur_filter(blur: ClipBlur, dest_w: int, dest_h: int, *, index: int = 0) -> str:
    """Soft gaussian region blur in post-fit canvas pixels.

    Uses split + gblur + soft rect mask + maskedmerge. Strength / feather are
    specified at 1080 tall and scale with ``dest_h``.
    """
    dest_w = even_dim(dest_w)
    dest_h = even_dim(dest_h)
    scale = dest_h / BLUR_REF_H
    sigma = max(0.5, float(blur.strength) * scale)
    feather = max(0.0, float(blur.feather) * scale)
    x0 = max(0, min(dest_w - 1, int(round(blur.x * dest_w))))
    y0 = max(0, min(dest_h - 1, int(round(blur.y * dest_h))))
    x1 = max(x0 + 1, min(dest_w, int(round((blur.x + blur.w) * dest_w))))
    y1 = max(y0 + 1, min(dest_h, int(round((blur.y + blur.h) * dest_h))))
    tag = _tag(blur.id, index)
    base, blr, msk, blurred, mask = f"{tag}a", f"{tag}b", f"{tag}m", f"{tag}blur", f"{tag}mask"
    # Soft rect: hard white box then gblur for feather (lum geq commas escaped).
    geq = f"lum='if(between(X\\,{x0}\\,{x1})*between(Y\\,{y0}\\,{y1})\\,255\\,0)'"
    mask_chain = f"format=gray,geq={geq}"
    if feather > 0.05:
        mask_chain += f",gblur=sigma={feather:.2f}"
    return (
        f"split=3[{base}][{blr}][{msk}];"
        f"[{blr}]gblur=sigma={sigma:.2f}[{blurred}];"
        f"[{msk}]{mask_chain}[{mask}];"
        f"[{base}][{blurred}][{mask}]maskedmerge"
    )


def soft_mask_blur_chain(blurs: list[ClipBlur], dest_w: int, dest_h: int) -> str:
    parts = [soft_mask_blur_filter(b, dest_w, dest_h, index=i) for i, b in enumerate(blurs) if b.w > 0 and b.h > 0]
    if not parts:
        return ""
    # Each segment ends unlabeled so the next split continues the chain via ','.
    return ",".join(parts)
