#!/usr/bin/env python3
"""Regenerate assets/flow-{dark,light}.svg.

Not run by CI: the diagram changes rarely, so run it by hand after editing
STAGES.

The stages are deliberately stack-neutral. An earlier version read
Request -> Interface -> Services -> Chains -> Settlement, which described the
cross-chain work accurately but, standing alone on the profile, implied
blockchain was the only thing on offer.
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "assets"
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

STAGES = ["Interface", "Services", "Data", "Infrastructure", "Ship"]
HEADING = "END TO END"

DARK = dict(name="dark", card="#161b22", stroke="#232c38", text="#e6edf3",
            muted="#6e7a8a", a1="#58a6ff", a3="#39d0d8", line="#2b3b52",
            core="#c9e2ff")
LIGHT = dict(name="light", card="#ffffff", stroke="#d8dee6", text="#111820",
             muted="#6a7583", a1="#0969da", a3="#0d9488", line="#ccd7e4",
             core="#ffffff")

X0, X1, CY, H = 150.0, 1050.0, 74.0, 150


def flow(p):
    n = len(STAGES)
    step = (X1 - X0) / (n - 1)
    xs = [X0 + step * i for i in range(n)]
    parts = [f'<line x1="{X0}" y1="{CY}" x2="{X1}" y2="{CY}" stroke="{p["line"]}" '
             f'stroke-width="2" stroke-linecap="round"/>']
    # one packet per segment, staggered, so motion reads across the full width
    for i in range(n - 1):
        parts.append(
            f'<circle r="3.4" fill="{p["a3"]}" filter="url(#fsoft)">'
            f'<animateMotion dur="2.6s" begin="{i * 0.52:.2f}s" repeatCount="indefinite" '
            f'path="M{xs[i]:.0f},{CY} L{xs[i + 1]:.0f},{CY}"/>'
            f'<animate attributeName="opacity" values="0;1;1;0" dur="2.6s" '
            f'begin="{i * 0.52:.2f}s" repeatCount="indefinite"/></circle>')
    for i, (x, label) in enumerate(zip(xs, STAGES)):
        per = 3.2 + i * 0.4
        parts.append(
            f'<circle cx="{x:.0f}" cy="{CY}" r="19" fill="{p["a1"]}" opacity="0.10">'
            f'<animate attributeName="r" values="16;22;16" dur="{per:.1f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values=".14;.04;.14" dur="{per:.1f}s" repeatCount="indefinite"/></circle>'
            f'<circle cx="{x:.0f}" cy="{CY}" r="8.5" fill="url(#fg)" filter="url(#fsoft)"/>'
            f'<circle cx="{x:.0f}" cy="{CY}" r="3.4" fill="{p["core"]}"/>'
            f'<text x="{x:.0f}" y="{CY + 42:.0f}" text-anchor="middle" font-size="14" '
            f'font-weight="600" fill="{p["text"]}" font-family="{FONT}">{label}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 {H}" width="1200" height="{H}" role="img" aria-label="{HEADING}: {', '.join(STAGES)}">
  <defs>
    <linearGradient id="fg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{p['a1']}"/><stop offset="100%" stop-color="{p['a3']}"/>
    </linearGradient>
    <filter id="fsoft" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="1200" height="{H}" rx="10" fill="{p['card']}" stroke="{p['stroke']}" stroke-width="1"/>
  <text x="600" y="34" text-anchor="middle" font-size="12" font-weight="600" letter-spacing="3.2"
        fill="{p['muted']}" font-family="{FONT}">{HEADING}</text>
  {''.join(parts)}
</svg>
'''


if __name__ == "__main__":
    for p in (DARK, LIGHT):
        (OUT / f"flow-{p['name']}.svg").write_text(flow(p))
    print("wrote flow SVGs:", " -> ".join(STAGES))
