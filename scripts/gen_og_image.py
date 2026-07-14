"""Gera a og:image (1200x630) do AegisFlow para preview em redes sociais.

Uso: python scripts/gen_og_image.py  → grava app/public/og-image.png
Requer Pillow (asset de build; não é dependência de runtime).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
OUT = Path(__file__).resolve().parent.parent / "app" / "public" / "og-image.png"

BG_TOP = (15, 23, 42)      # #0f172a
BG_BOT = (10, 15, 28)      # mais escuro
TEAL = (94, 234, 212)      # #5eead4
WHITE = (248, 250, 252)    # #f8fafc
MUTED = (148, 163, 184)    # #94a3b8

SEGOE_B = "C:/Windows/Fonts/segoeuib.ttf"
SEGOE = "C:/Windows/Fonts/segoeui.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def main() -> None:
    img = Image.new("RGB", (W, H), BG_TOP)
    px = img.load()
    # gradiente vertical
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)

    # brilho teal (radial) no canto superior direito
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 520, -260, W + 160, 300], fill=(20, 184, 166, 70))
    glow = glow.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(120))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)

    M = 90  # margem
    # marca
    d.text((M, 70), "∞", font=font(SEGOE_B, 64), fill=TEAL)
    d.text((M + 70, 84), "AegisFlow", font=font(SEGOE_B, 46), fill=WHITE)

    # headline
    d.text((M, 210), "Sua fatura de IA,", font=font(SEGOE_B, 82), fill=WHITE)
    d.text((M, 300), "até 70% menor.", font=font(SEGOE_B, 82), fill=TEAL)

    # subline
    d.text(
        (M, 430),
        "Gateway de LLM  ·  BYOK sem markup  ·  Cache semântico",
        font=font(SEGOE, 34),
        fill=MUTED,
    )
    d.text(
        (M, 480),
        "Dados no Brasil  ·  LGPD  ·  aegisflow.tech",
        font=font(SEGOE, 34),
        fill=MUTED,
    )

    # barra de acento inferior
    d.rectangle([0, H - 10, W, H], fill=TEAL)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"OK -> {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
