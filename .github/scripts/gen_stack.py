#!/usr/bin/env python3
"""Regenerate assets/stack-{dark,light}.svg.

Not run by CI: the stack changes rarely, so it is invoked by hand after
editing ROWS. Kept in the repo because the layout needs measured text
widths, which are painful to recreate from scratch.

WIDTHS were measured in a real browser with canvas measureText at the exact
font and size used below. After changing ROWS, re-measure any new label or it
falls back to a rough estimate and the pill may not fit its text.
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "assets"
FONT = ("-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,"
        "\'Helvetica Neue\',Arial,sans-serif")

ROWS = [
    ("Core", ["TypeScript", "Python", "React", "React Native", "Next.js"]),
    ("Web3", ["viem", "wagmi", "ethers.js", "Polkadot.js", "Solidity", "Hardhat", "LayerZero"]),
    ("Backend", ["FastAPI", "NestJS", "PostgreSQL", "SQLAlchemy", "Prisma", "Socket.io"]),
    ("Interface", ["Tailwind", "MUI", "TanStack Query", "Zustand", "Three.js", "R3F", "Framer Motion"]),
    ("Platform", ["Docker", "Turborepo", "Prometheus", "Grafana"]),
]

WIDTHS = {
    "TypeScript": 71.78,
    "Python": 46.79,
    "React": 37.8,
    "React Native": 83.59,
    "Next.js": 45.8,
    "viem": 31.42,
    "wagmi": 42.94,
    "ethers.js": 57.21,
    "Polkadot.js": 72.97,
    "Solidity": 49.27,
    "Hardhat": 53.26,
    "LayerZero": 66.37,
    "FastAPI": 50.1,
    "NestJS": 47.46,
    "PostgreSQL": 78.74,
    "SQLAlchemy": 84.6,
    "Prisma": 45.29,
    "Socket.io": 61.52,
    "Tailwind": 53.66,
    "MUI": 26.35,
    "TanStack Query": 104.67,
    "Zustand": 54.49,
    "Three.js": 53.46,
    "R3F": 25.99,
    "Framer Motion": 96.17,
    "Docker": 46.96,
    "Turborepo": 68.51,
    "Prometheus": 79.77,
    "Grafana": 52.15
}
LABELS = {
    "Core": 36.2,
    "Web3": 37.98,
    "Backend": 63.16,
    "Interface": 71.9,
    "Platform": 70.62
}

DARK = dict(name="dark", card="#161b22", stroke="#232c38",
            chip="#1c2431", chip_stroke="#2b3542", chip_text="#c9d3e0",
            a1="#58a6ff", a2="#a371f7", a3="#39d0d8")
LIGHT = dict(name="light", card="#ffffff", stroke="#d8dee6",
             chip="#f2f5f9", chip_stroke="#dde4ec", chip_text="#26313f",
             a1="#0969da", a2="#8250df", a3="#0d9488")

PAD_X, CHIP_H, GAP, ROW_GAP = 13.0, 30.0, 9.0, 16.0
X_CHIPS, X_RIGHT, Y_TOP = 196.0, 1140.0, 34.0


def layout():
    placed, y = [], Y_TOP
    for label, items in ROWS:
        x, line_y, lines, row = X_CHIPS, y, 1, []
        for t in items:
            cw = WIDTHS.get(t, len(t) * 8.2) + PAD_X * 2
            if x + cw > X_RIGHT and row:
                x, line_y, lines = X_CHIPS, line_y + CHIP_H + GAP, lines + 1
            row.append((t, x, line_y, cw))
            x += cw + GAP
        placed.append((label, y, row, lines))
        y = line_y + CHIP_H + ROW_GAP
    # Rows are left-packed and ragged, so shift the block to sit optically centred.
    left = 170.0 - max(LABELS[l] for l, _ in ROWS)
    right = max((x + cw) for _, _, row, _ in placed for _, x, _, cw in row)
    return placed, y + 14, (1200.0 - (right - left)) / 2.0 - left


def stack(p):
    placed, height, dx = layout()
    parts = []
    for label, y, row, lines in placed:
        h = lines * CHIP_H + (lines - 1) * GAP
        parts.append(
            f'<text x="170" y="{y + 20:.1f}" text-anchor="end" font-size="13" font-weight="600" '
            f'letter-spacing="1.6" fill="{p["a3"]}" font-family="{FONT}">{label.upper()}</text>'
            f'<rect x="181" y="{y:.1f}" width="2" height="{h:.1f}" rx="1" fill="url(#kgrad)" opacity="0.5"/>')
        for t, x, cy, cw in row:
            parts.append(
                f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{CHIP_H}" rx="{CHIP_H / 2}" '
                f'fill="{p["chip"]}" stroke="{p["chip_stroke"]}" stroke-width="1"/>'
                f'<text x="{x + cw / 2:.1f}" y="{cy + 19.5:.1f}" text-anchor="middle" font-size="14" '
                f'font-weight="500" fill="{p["chip_text"]}" font-family="{FONT}">{t}</text>')
    alt = "; ".join(f"{l}: {', '.join(i)}" for l, i in ROWS)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 {height:.0f}" width="1200" height="{height:.0f}" role="img" aria-label="{alt}">
  <defs>
    <linearGradient id="kgrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{p['a1']}"/><stop offset="100%" stop-color="{p['a3']}"/>
    </linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{p['a2']}" stop-opacity="0"/><stop offset="50%" stop-color="{p['a2']}" stop-opacity="0.5"/><stop offset="100%" stop-color="{p['a2']}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="{height:.0f}" rx="10" fill="{p['card']}" stroke="{p['stroke']}" stroke-width="1"/>
  <g transform="translate({dx:.1f},0)">{"".join(parts)}</g>
  <rect x="0" y="{height - 3:.1f}" width="300" height="2" rx="1" fill="url(#sheen)">
    <animate attributeName="x" values="-300;1200;-300" dur="11s" repeatCount="indefinite"/>
  </rect>
</svg>
'''


if __name__ == "__main__":
    for p in (DARK, LIGHT):
        (OUT / f"stack-{p['name']}.svg").write_text(stack(p))
    _, h, dx = layout()
    print(f"wrote stack SVGs (height {h:.0f}, dx {dx:.1f})")
