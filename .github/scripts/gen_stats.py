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
import hashlib
import json
import os
import pathlib
import re
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

# Repo/org counts need a `repo`-scoped token to see private and org
# repositories, which is more access than this workflow should hold. They move
# slowly, so they are constants. Recompute with a repo-scoped token via:
#   GET /user/repos?affiliation=owner            -> REPOS_OWNED
#   GET /repos/{full_name}/commits?author=USER   -> REPOS_EXTERNAL / ORGS
# Last measured 2026-08: 75 owned (46 public, 29 private); 29 external repos
# with commits across 11 owners.
REPOS_OWNED = 75
REPOS_EXTERNAL = 29
ORGS = 11

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
    """All-time commit + contribution totals, summed per year.

    contributionsCollection only covers a one-year window, so every year GitHub
    has on record is queried in a single aliased request and summed. Returns
    (commits, contributions, ok) where ok is False if the token is under-scoped.
    """
    tok = os.environ.get("STATS_TOKEN")
    node = "viewer"
    if not tok:
        tok = os.environ["GITHUB_TOKEN"]
        node = f'user(login: "{USER}")'
        print("STATS_TOKEN not set -> public-only numbers")

    years = _post("https://api.github.com/graphql",
                  {"query": "query { %s { contributionsCollection { contributionYears } } }" % node},
                  tok)["data"][node.split("(")[0]]["contributionsCollection"]["contributionYears"]

    # One aliased request instead of one round-trip per year.
    blocks = "".join(
        f'y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z")'
        '{ totalCommitContributions restrictedContributionsCount'
        ' contributionCalendar { totalContributions } } '
        for y in years)
    d = _post("https://api.github.com/graphql",
              {"query": "query { %s { %s } }" % (node, blocks)}, tok)
    if "errors" in d:
        raise SystemExit(f"GraphQL error: {d['errors']}")
    v = d["data"][node.split("(")[0]]

    commits = sum(v[f"y{y}"]["totalCommitContributions"] for y in years)
    restricted = sum(v[f"y{y}"]["restrictedContributionsCount"] for y in years)
    total = sum(v[f"y{y}"]["contributionCalendar"]["totalContributions"] for y in years)

    # Scope guard: without read:user, private commits are reported as
    # "restricted" instead of counted, collapsing commits to public-only
    # (observed all-time: 4,397 commits / 15,689 restricted vs the true split).
    # Warn, don't fail. contributionCalendar.totalContributions is
    # scope-independent, so the displayed panel stays correct even when the
    # token loses read:user -- only the (unused) commit split degrades. Aborting
    # the run would stop good updates over a metric nobody sees.
    ok = restricted <= commits
    if not ok:
        print(f"WARNING: STATS_TOKEN looks under-scoped ({restricted:,} restricted vs "
              f"{commits:,} counted commits). Contributions are unaffected; add the "
              "read:user scope if the commit split is ever needed again.")
    print(f"years {min(years)}-{max(years)}: {commits:,} commits, {total:,} contributions")
    return commits, total, ok


def stars():
    """Stars across public repos -- no auth needed, so no extra token scope."""
    total, page = 0, 1
    while True:
        batch = _get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}")
        if not batch:
            break
        total += sum(r["stargazers_count"] for r in batch)
        page += 1
        if len(batch) < 100:
            break
    return total


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
            f'<text x="{cx:.0f}" y="76" text-anchor="middle" font-size="44" font-weight="700" '
            f'fill="url(#sgrad)" font-family="{FONT}">{val}</text>'
            f'<text x="{cx:.0f}" y="106" text-anchor="middle" font-size="16.5" font-weight="600" '
            f'fill="{p["text"]}" font-family="{FONT}">{label}</text>'
            f'<text x="{cx:.0f}" y="128" text-anchor="middle" font-size="13" '
            f'fill="{p["muted"]}" font-family="{FONT}">{sub}</text>')
        if i:
            parts.append(f'<rect x="{w * i:.0f}" y="50" width="1" height="78" fill="{p["stroke"]}"/>')

    parts.append(f'<rect x="60" y="158" width="1080" height="1" fill="{p["stroke"]}"/>')
    parts.append(f'<text x="60" y="190" font-size="13" font-weight="600" letter-spacing="3" '
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
            f'<text x="{lx + 18:.1f}" y="{BAR_Y + 58:.0f}" font-size="14.5" font-weight="500" '
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
    commits, total_contrib, _ = contributions()
    star_count = stars()
    dl = downloads()

    cells = [
        (f"{total_contrib:,}", "Contributions", "all time, since 2015"),
        (str(REPOS_OWNED + REPOS_EXTERNAL), "Repositories",
         f"{REPOS_OWNED} mine, {REPOS_EXTERNAL} external"),
        (str(ORGS), "Organizations", "contributed to"),
        (f"{star_count:,}", "Stars", "earned"),
    ]
    if dl:
        cells.append((human(dl), "Downloads", "PyPI, all time"))

    for p in (DARK, LIGHT):
        (OUT / f"stats-{p['name']}.svg").write_text(render(p, cells))
    print("updated:", " | ".join(f"{v} {l}" for v, l, _ in cells))
    _sync_readme(cells)


def _sync_readme(cells):
    """Point the README at current asset content and keep alt text truthful.

    Every asset URL carries a ?v= tag derived from that asset's own content
    hash. With a fixed tag the URL never changes, so browsers and GitHub's
    image proxy keep serving a previous render after the file is updated.
    Covers hero/flow/stack too, not just stats: those are edited by hand and
    hit the same problem.
    """
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = original = readme.read_text()

    for asset in ("hero", "flow", "stack", "stats"):
        blobs = b""
        for variant in ("dark", "light"):
            p = OUT / f"{asset}-{variant}.svg"
            if p.exists():
                blobs += p.read_bytes()
        if not blobs:
            continue
        digest = hashlib.sha1(blobs).hexdigest()[:8]
        text = re.sub(rf"(assets/{asset}-(?:dark|light)\.svg)\?v=[A-Za-z0-9]+",
                      rf"\1?v={digest}", text)

    alt = ", ".join(f"{v} {l.lower()} ({s})" for v, l, s in cells) + "."
    alt = alt.replace("&#38;", "and")
    text = re.sub(r'(<img src="[^"]*assets/stats-dark\.svg[^"]*" alt=")[^"]*(")',
                  lambda m: m.group(1) + alt + m.group(2), text)

    if text != original:
        readme.write_text(text)
        print("README synced (asset ?v tags refreshed)")


if __name__ == "__main__":
    main()
