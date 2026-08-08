#!/usr/bin/env python3
"""Regenerate assets/stats-{dark,light}.svg from live data.

Run by .github/workflows/refresh-stats.yml.

Token behaviour
---------------
STATS_TOKEN (classic PAT, scope: read:user) queries `viewer`, which is the only
way to read restrictedContributionsCount -- the private/org commit count. If the
secret is absent the script falls back to GITHUB_TOKEN and the public `user()`
query, and drops the "Private" cell rather than printing a wrong number.

The language split is a constant below, not recomputed here: reading it live
would need a token with `repo` scope to see private repositories, and the
distribution moves by fractions of a percent per month. Recompute it
occasionally with the one-liner in LANGS' comment.
"""
import json
import os
import pathlib
import urllib.error
import urllib.request

USER = "dev-aly3n"
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "assets"
PACKAGES = ("aipager", "dtach-bin")

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

DARK = dict(name="dark", card="#161b22", stroke="#232c38", text="#e6edf3",
            muted="#6e7a8a", a1="#58a6ff", a2="#a371f7", a3="#39d0d8",
            other="#4a5563")
LIGHT = dict(name="light", card="#ffffff", stroke="#d8dee6", text="#111820",
             muted="#6a7583", a1="#0969da", a2="#8250df", a3="#0d9488",
             other="#9aa4b2")

# Summed /languages bytes across owned non-fork repos (public + private).
# Refresh with a `repo`-scoped token when it feels stale; last taken 2026-08.
LANGS = [
    ("TypeScript", 40.8, "#3178c6"),
    ("Python", 23.5, "#3572A5"),
    ("CSS", 17.0, "#663399"),
    ("JavaScript", 7.3, "#f1e05a"),
    ("Solidity", 6.3, "#AA6746"),
    ("Other", 5.1, None),
]

H = 300
BAR_X, BAR_W, BAR_Y, BAR_H = 60.0, 1080.0, 206.0, 16.0


def _post(url, payload, token):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": f"{USER}-profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def contributions():
    """(stats dict, private_available). Prefers the private-aware viewer query."""
    # repositoriesContributedTo is deliberately not queried: it only counts
    # repos the token can see, so a read:user-scoped token reports 8 instead of
    # the real 25. Widening the token to `repo` just to fix one cell is not
    # worth the blast radius, so the cell is dropped instead.
    fields = ("contributionsCollection { totalCommitContributions "
              "restrictedContributionsCount contributionCalendar { totalContributions } }")
    tok = os.environ.get("STATS_TOKEN")
    if tok:
        q = "query { viewer { %s } }" % fields
        node, private_ok = "viewer", True
    else:
        tok = os.environ["GITHUB_TOKEN"]
        q = 'query { user(login: "%s") { %s } }' % (USER, fields)
        node, private_ok = "user", False
        print("STATS_TOKEN not set -> public-only numbers, hiding Private cell")

    d = _post("https://api.github.com/graphql", {"query": q}, tok)
    if "errors" in d:
        raise SystemExit(f"GraphQL error: {d['errors']}")
    v = d["data"][node]
    c = v["contributionsCollection"]

    # Scope guard. restrictedContributionsCount means "contributions the viewer
    # may not see the detail of", so it is scope-dependent: with read:user your
    # own private commits land in totalCommitContributions, without it they all
    # fall into restricted and totalCommitContributions collapses to public-only
    # (observed: 4,475/852 with the scope vs 436/5,093 without).
    # Publishing the second shape would badly understate the commit count, so
    # fail loudly rather than write a wrong panel.
    if private_ok:
        total = c["contributionCalendar"]["totalContributions"] or 1
        if c["restrictedContributionsCount"] / total > 0.5:
            raise SystemExit(
                "STATS_TOKEN looks under-scoped: "
                f"{c['restrictedContributionsCount']} of {total} contributions came back "
                "restricted, which means commits would publish as public-only. "
                "Regenerate the token with the read:user scope."
            )
        if not c["restrictedContributionsCount"]:
            private_ok = False
    return {
        "contrib": c["contributionCalendar"]["totalContributions"],
        "commits": c["totalCommitContributions"],
        "private": c["restrictedContributionsCount"],
    }, private_ok


def downloads():
    total = 0
    for p in PACKAGES:
        try:
            total += sum(x["downloads"]
                         for x in _get(f"https://pypistats.org/api/packages/{p}/overall")["data"])
        except (urllib.error.URLError, KeyError, ValueError) as e:
            print(f"pypistats {p} unavailable ({e}); excluded from total")
    return total


def human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def render(p, cells):
    parts, w = [], 1200 / len(cells)
    for i, (val, label, sub) in enumerate(cells):
        cx = w * i + w / 2
        parts.append(
            f'<text x="{cx:.0f}" y="74" text-anchor="middle" font-size="38" font-weight="700" '
            f'fill="url(#sgrad)" font-family="{FONT}">{val}</text>'
            f'<text x="{cx:.0f}" y="101" text-anchor="middle" font-size="14" font-weight="600" '
            f'fill="{p["text"]}" font-family="{FONT}">{label}</text>'
            f'<text x="{cx:.0f}" y="122" text-anchor="middle" font-size="11.5" '
            f'fill="{p["muted"]}" font-family="{FONT}">{sub}</text>')
        if i:
            parts.append(f'<rect x="{w * i:.0f}" y="50" width="1" height="78" fill="{p["stroke"]}"/>')

    parts.append(f'<rect x="60" y="158" width="1080" height="1" fill="{p["stroke"]}"/>')
    parts.append(f'<text x="60" y="190" font-size="11.5" font-weight="600" letter-spacing="3" '
                 f'fill="{p["muted"]}" font-family="{FONT}">LANGUAGES BY CODE VOLUME</text>')

    # Authentic linguist colours; TypeScript and Python are near-identical blues,
    # so a hairline gap keeps the segments readable.
    gap, segs, x = 2.0, [], BAR_X
    for i, (_, pct, colour) in enumerate(LANGS):
        seg = BAR_W * pct / 100.0
        draw = seg - (gap if i < len(LANGS) - 1 else 0)
        segs.append(f'<rect x="{x:.2f}" y="{BAR_Y}" width="{draw:.2f}" height="{BAR_H}" '
                    f'fill="{colour or p["other"]}"/>')
        x += seg
    parts.append(
        f'<g clip-path="url(#barclip)">{"".join(segs)}'
        f'<rect x="{BAR_X}" y="{BAR_Y}" width="180" height="{BAR_H}" fill="url(#gloss)" opacity="0.55">'
        f'<animate attributeName="x" values="{BAR_X - 180};{BAR_X + BAR_W};{BAR_X - 180}" '
        f'dur="9s" repeatCount="indefinite"/></rect></g>')

    step = BAR_W / len(LANGS)
    for i, (name, pct, colour) in enumerate(LANGS):
        lx = BAR_X + step * i
        parts.append(
            f'<circle cx="{lx + 5:.1f}" cy="{BAR_Y + 52:.0f}" r="5" fill="{colour or p["other"]}"/>'
            f'<text x="{lx + 18:.1f}" y="{BAR_Y + 57:.0f}" font-size="13" font-weight="500" '
            f'fill="{p["text"]}" font-family="{FONT}">{name} '
            f'<tspan fill="{p["muted"]}" font-weight="400">{pct}%</tspan></text>')

    alt = (", ".join(f"{v} {l.lower()} ({s})" for v, l, s in cells) +
           ". Languages by code volume: " + ", ".join(f"{n} {v}%" for n, v, _ in LANGS))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 {H}" width="1200" height="{H}" role="img" aria-label="{alt}">
  <defs>
    <linearGradient id="sgrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{p['a1']}"/><stop offset="50%" stop-color="{p['a2']}"/><stop offset="100%" stop-color="{p['a3']}"/>
    </linearGradient>
    <linearGradient id="gloss" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/><stop offset="50%" stop-color="#ffffff" stop-opacity="0.30"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="barclip"><rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="{BAR_H}" rx="{BAR_H / 2}"/></clipPath>
  </defs>
  <rect width="1200" height="{H}" rx="10" fill="{p['card']}" stroke="{p['stroke']}" stroke-width="1"/>
  {''.join(parts)}
</svg>
'''


def main():
    s, private_ok = contributions()
    dl = downloads()
    cells = [(f"{s['contrib']:,}", "Contributions", "past 12 months"),
             (f"{s['commits']:,}", "Commits", "authored")]
    if private_ok:
        cells.append((f"{s['private']:,}", "Private", "org &#38; private repos"))
    if dl:
        cells.append((human(dl), "Downloads", "PyPI, all time"))

    for p in (DARK, LIGHT):
        (OUT / f"stats-{p['name']}.svg").write_text(render(p, cells))
    print("updated:", " | ".join(f"{v} {l}" for v, l, _ in cells))


if __name__ == "__main__":
    main()
