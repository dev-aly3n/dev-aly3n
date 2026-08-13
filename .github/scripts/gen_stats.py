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
import datetime
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

# Summed /languages bytes across the 90 repositories actually worked in: 61
# owned non-fork plus 29 external repos with commits by this account. Counting
# only owned repos was misleading, since the heaviest code lives in org repos.
#
# Styling and markup are excluded (see SKIP below). They are not programming
# languages and they bloat with generated files: CSS alone was showing 6.9%,
# and 14.4% back when only owned repos were counted.
#
# Needs a repo-scoped token, so these are constants rather than live values.
# Recompute occasionally; last measured 2026-08.
# SKIP = CSS, SCSS, Sass, Less, HTML, MDX, Markdown, SVG, Vue, Handlebars, EJS, Pug
LANGS = [
    ("TypeScript", 69.5, "#3178c6"),
    ("Python", 14.9, "#3572A5"),
    ("JavaScript", 6.1, "#f1e05a"),
    ("Solidity", 5.5, "#AA6746"),
    ("Rust", 2.7, "#dea584"),
    ("Other", 1.3, None),
]

# Repo/org counts need a `repo`-scoped token to see private and org
# repositories, which is more access than this workflow should hold. They move
# slowly, so they are constants. Recompute with a repo-scoped token via:
#   GET /user/repos?affiliation=owner            -> REPOS_OWNED
#   GET /repos/{full_name}/commits?author=USER   -> REPOS_EXTERNAL / ORGS
# Last measured 2026-08: 76 owned (46 public, 30 private); 29 external repos
# with commits across 11 owners.
REPOS_OWNED = 76
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
    """(all-time total, {package: last-30-days}).

    Both figures come from the single /overall payload. The /recent endpoint
    returns 429 far more often, and calling it separately meant the monthly
    number kept vanishing while the all-time one succeeded.
    """
    total, recent = 0, {}
    for p in PACKAGES:
        try:
            rows = _get(f"https://pypistats.org/api/packages/{p}/overall")["data"]
        except (urllib.error.URLError, KeyError, ValueError) as e:
            print(f"pypistats {p} unavailable ({e}); excluded from total")
            continue
        # The payload carries two overlapping series, with_mirrors and
        # without_mirrors. Summing the rows blindly double-counts: it reported
        # 42,338 where the real figure is 9,964. without_mirrors is the honest
        # one, excluding mirror and CI traffic, and matches what shields shows.
        real = [x for x in rows if x.get("category") == "without_mirrors"]
        total += sum(x["downloads"] for x in real)
        recent[p] = sum(x["downloads"] for x in sorted(real, key=lambda x: x["date"])[-30:])
    return total, recent


# Approximate advance widths for the badge font at 11px. Shields does the same
# thing; exact metrics are not worth a browser dependency inside CI. Padding is
# generous so a slight underestimate never clips the text.
_NARROW = set("iljtfr.,:;'|! ")
_WIDE = set("mwMW@")


def _text_w(t):
    return sum(4.0 if c in _NARROW else 9.2 if c in _WIDE else 6.7 for c in t)


def badge(label, value, colour="#3775A9"):
    """Self-hosted flat badge.

    shields.io's pypi/dm endpoint intermittently renders the literal text
    "rate limited by upstream service" onto the profile, so the dynamic PyPI
    badges are generated here instead of fetched by the reader's browser.
    """
    lw, vw, h = _text_w(label) + 20, _text_w(value) + 20, 20
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{lw + vw:.0f}" height="{h}" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <clipPath id="c"><rect width="{lw + vw:.0f}" height="{h}" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#c)">
    <rect width="{lw:.0f}" height="{h}" fill="#555"/>
    <rect x="{lw:.0f}" width="{vw:.0f}" height="{h}" fill="{colour}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="{FONT}" font-size="11">
    <text x="{lw / 2:.0f}" y="14">{label}</text>
    <text x="{lw + vw / 2:.0f}" y="14" font-weight="600">{value}</text>
  </g>
</svg>
'''


def last_week():
    """(contributions, repos) over the trailing 7 days, or None.

    A yearly total says someone was once busy. A 7-day figure says they are
    working right now, which is what a visitor is judging.
    """
    tok = os.environ.get("STATS_TOKEN")
    node = "viewer"
    if not tok:
        tok = os.environ.get("GITHUB_TOKEN", "")
        node = f'user(login: "{USER}")'
    now = datetime.datetime.now(datetime.timezone.utc)
    frm = now - datetime.timedelta(days=7)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    q = (f'query {{ {node} {{ contributionsCollection('
         f'from:"{frm.strftime(stamp)}",to:"{now.strftime(stamp)}") {{ '
         f'contributionCalendar {{ totalContributions }} '
         f'commitContributionsByRepository(maxRepositories:100) {{ repository {{ id }} }} '
         f'}} }} }}')
    try:
        d = _post("https://api.github.com/graphql", {"query": q}, tok)
    except Exception as e:
        print(f"weekly window request failed: {e}")
        return None
    if "errors" in d:
        print(f"weekly window GraphQL error: {d['errors']}")
        return None
    c = d["data"][node.split("(")[0]]["contributionsCollection"]
    # Private repos are not enumerable on a read:user token, so the repo count
    # is best-effort and dropped when it comes back empty.
    return (c["contributionCalendar"]["totalContributions"],
            len(c.get("commitContributionsByRepository") or []))


def releases(repo):
    """(latest tag, ISO date, total count) for a repo, or None on failure."""
    try:
        tok = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases?per_page=100",
            headers={"Authorization": f"token {tok}", "User-Agent": f"{USER}-profile-stats"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.load(r)
        published = [x for x in rows if x.get("published_at")]
        if not published:
            return None
        latest = max(published, key=lambda x: x["published_at"])
        return latest["tag_name"], latest["published_at"][:10], len(rows)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(f"releases {repo} unavailable ({e})")
        return None


def version(package):
    try:
        return _get(f"https://pypi.org/pypi/{package}/json")["info"]["version"]
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(f"pypi version {package} unavailable ({e})")
        return None


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
    dl, recent = downloads()

    cells = [
        (f"{total_contrib:,}", "Contributions", "all time, since 2015"),
        (str(REPOS_OWNED + REPOS_EXTERNAL), "Repositories",
         f"{REPOS_OWNED} mine, {REPOS_EXTERNAL} external"),
        (str(ORGS), "Organizations", "contributed to"),
        (f"{star_count:,}", "Stars", "earned"),
    ]
    if dl:
        cells.append((human(dl), "Downloads", "PyPI, all time"))

    for pkg in PACKAGES:
        v, m = version(pkg), recent.get(pkg)
        parts = [f"v{v}"] if v else []
        if m:
            parts.append(f"{human(m)}/month")
        else:
            # pypistats 429s intermittently. Rather than silently dropping the
            # figure from the badge, reuse the last value we committed.
            prev = OUT / f"badge-{pkg}.svg"
            if prev.exists():
                carried = re.search(r"(\S+/month)", prev.read_text())
                if carried:
                    parts.append(carried.group(1))
                    print(f"  carried previous figure for {pkg}: {carried.group(1)}")
        if parts:
            (OUT / f"badge-{pkg}.svg").write_text(badge(pkg, " \u00b7 ".join(parts)))
            print(f"badge-{pkg}.svg: {' / '.join(parts)}")

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

    assets = ["hero", "flow", "stack", "stats"] + [f"badge-{p}" for p in PACKAGES]
    for asset in assets:
        blobs = b""
        for variant in ("dark", "light"):
            p = OUT / f"{asset}-{variant}.svg"
            if p.exists():
                blobs += p.read_bytes()
        single = OUT / f"{asset}.svg"
        if single.exists():
            blobs += single.read_bytes()
        if not blobs:
            continue
        digest = hashlib.sha1(blobs).hexdigest()[:8]
        text = re.sub(rf"(assets/{asset}(?:-(?:dark|light))?\.svg)\?v=[A-Za-z0-9]+",
                      rf"\1?v={digest}", text)

    alt = ", ".join(f"{v} {l.lower()} ({s})" for v, l, s in cells) + "."
    alt = alt.replace("&#38;", "and")
    text = re.sub(r'(<img src="[^"]*assets/stats-dark\.svg[^"]*" alt=")[^"]*(")',
                  lambda m: m.group(1) + alt + m.group(2), text)

    week = last_week()
    if week and week[0]:
        total, repos = week
        tail = f" across {repos} repositories" if repos else ""
        text = re.sub(r"(<!--WEEK-->).*?(<!--/WEEK-->)",
                      lambda _m: f"<!--WEEK-->\n  <sub>Last 7 days: <strong>{total}</strong> "
                                 f"contributions{tail}</sub>\n  <!--/WEEK-->",
                      text, flags=re.S)
        print(f"weekly line: {total} contributions / {repos} repos")

    # Release recency, rewritten between markers. Thirty-plus releases is the
    # strongest available signal that the project is actively maintained, and a
    # hardcoded version would contradict the badge within a week.
    rel = releases("dev-aly3n/aipager")
    if rel:
        tag, date, count = rel
        y, m, d = date.split("-")
        month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
        line = (f"<sub>Latest release <strong>{tag}</strong> on {int(d)} {month} {y}"
                f" &#183; {count} releases so far</sub>")
        text = re.sub(r"(<!--RELEASES-->).*?(<!--/RELEASES-->)",
                      lambda _m: f"<!--RELEASES-->\n{line}\n<!--/RELEASES-->",
                      text, flags=re.S)
        print(f"release line: {tag} / {date} / {count} releases")

    if text != original:
        readme.write_text(text)
        print("README synced (asset ?v tags refreshed)")


if __name__ == "__main__":
    main()
