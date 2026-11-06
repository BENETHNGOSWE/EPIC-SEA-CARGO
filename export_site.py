#!/usr/bin/env python3
"""Make the folder you actually deploy: dist/

Why this exists: the repository is a WordPress theme mirror - about 750 files, of which the
four built pages load roughly 100. Pushing the mirror would publish the theme's own source (a
licence problem), ship a 1.3 MB wp-json dump and a few hundred empty stub files, and give
Coolify nothing to build. dist/ is the opposite: the home page at /, one folder per page, and
only the files those pages reference.

The pages are then rewritten rather than pattern-poked: every href, src, srcset, inline url()
and icon meta is resolved to a real file, mapped to where that file lands in dist, and made
relative again from the page's new folder - which is the only way the home page can move from
/epic-home/ to / without a single broken link. Finally dist is checked from the inside: every
reference in it must resolve to a file in it, so an asset that exists in the mirror but was not
copied cannot survive the export.

    python3 export_site.py           # writes dist/ and reports what it took and what it left
"""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
SITE = "https://epicseacargo.com"
# built folder -> folder inside dist; the home page lands at the root, so / and not /epic-home/
PAGES = [("epic-home", ""), ("about", "about"), ("our-services", "our-services"),
         ("contact-us", "contact-us")]
PAGE_MAP = {f"{f}/index.html": (os.path.join(d, "index.html") if d else "index.html")
            for f, d in PAGES}
SKIP_EXT = {".php", ".md", ".json", ".map", ".txt"}
EXT = re.compile(r"""(?:src|href|poster|imagesrcset)\s*=\s*["']([^"']+)["']""", re.I)
SRCSET = re.compile(r"""srcset\s*=\s*["']([^"']+)["']""", re.I)
ICON = re.compile(r"""(content=")([^"]*(?:\.\./|\./)?wp-content/[^"]*)(")""", re.I)
URLCSS = re.compile(r"""url\(\s*['"]?([^'")]+)""", re.I)


def external(u):
    return not u or u.startswith(("#", "mailto:", "tel:", "data:", "javascript:",
                                 "http://", "https://", "//"))


def resolve(u, base):
    """href/src as written -> path relative to the repo, or None if it points out of the site."""
    if external(u):
        return None
    p = os.path.normpath(os.path.join(base, u.split("?")[0].split("#")[0]))
    if os.path.isdir(p):
        p = os.path.join(p, "index.html")
    r = os.path.relpath(p, ROOT)
    return None if r.startswith("..") else r.replace(os.sep, "/")


def re_page(html, src_base, new_dir):
    """Rewrite every local reference in a page for its new folder, resolving each one first."""
    def rel_to(repo_rel, keep_query):
        target = PAGE_MAP.get(repo_rel, repo_rel)
        out = os.path.relpath(target, new_dir or ".").replace(os.sep, "/")
        if out == ".":
            out = "./"
        return out + (keep_query if keep_query else "")

    def sub_attr(m):
        whole, val = m.group(0), m.group(1)
        q = re.search(r"[?#].*$", val)
        r = resolve(val, src_base)
        if r is None:
            return whole
        return whole[:m.start(1) - m.start(0)] + rel_to(r, q.group(0) if q else "") + whole[m.end(1) - m.start(0):]

    def sub_srcset(m):
        bits = []
        for cand in m.group(1).split(","):
            d = cand.strip().split(" ")
            q = re.search(r"[?#].*$", d[0])
            r = resolve(d[0], src_base)
            d[0] = rel_to(r, q.group(0) if q else "") if r else d[0]
            bits.append(" ".join(d))
        return m.group(0)[:m.start(1) - m.start(0)] + ", ".join(bits) + m.group(0)[m.end(1) - m.start(0):]

    def sub_url(m):
        val = m.group(1)
        r = resolve(val, src_base)
        if r is None:
            return m.group(0)
        q = re.search(r"[?#].*$", val)
        return "url(" + rel_to(r, q.group(0) if q else "") + ")"

    def sub_icon(m):
        r = resolve(m.group(2), src_base)
        if r is None:
            return m.group(0)
        return m.group(1) + rel_to(r, "") + m.group(3)

    html = EXT.sub(sub_attr, html)
    html = SRCSET.sub(sub_srcset, html)
    html = ICON.sub(sub_icon, html)
    return re.sub(r"""url\(\s*['"]?([^'")]+)['"]?\)""", sub_url, html)


def refs(path, root, is_html):
    """Everything a file pulls in, resolved against that file's own folder."""
    txt = open(path, encoding="utf-8", errors="ignore").read()
    base = os.path.dirname(path)
    out = []
    if is_html:
        out += [m.group(1) for m in EXT.finditer(txt)]
        out += [c.strip().split(" ")[0] for m in SRCSET.finditer(txt) for c in m.group(1).split(",")]
        out += [m.group(2) for m in ICON.finditer(txt)]
        out += URLCSS.findall(txt)
    elif path.endswith(".css"):
        out += URLCSS.findall(txt)
    keep = []
    for u in out:
        if external(u):
            continue
        p = os.path.normpath(os.path.join(base, u.split("?")[0].split("#")[0]))
        if os.path.isdir(p):
            p = os.path.join(p, "index.html")
        r = os.path.relpath(p, root)
        if r.startswith(".."):
            continue                                   # outside the artifact (external or root link)
        keep.append(r.replace(os.sep, "/"))
    return keep


def mirror_root():
    """Copy the verified home page and error page to the repository root.

    The mirror's own home page lives in home-01/ (that is what the builder reads), so the root of
    this branch can hold the real website instead. It means a server that ends up pointing at the
    SOURCE branch still shows Epic Sea Cargo rather than the theme's demo page. Only ever runs on
    an artifact that has just passed the self-check above.
    """
    moved = []
    for f in ("index.html", "404.html", "robots.txt", "sitemap.xml"):
        src = os.path.join(DIST, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(ROOT, f))
            moved.append(f)
    if moved:
        print("  mirrored to the source root (so a wrong-branch checkout still shows your site): "
              + ", ".join(moved))


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    queue = []
    for folder, dest in PAGES:
        src = os.path.join(ROOT, folder, "index.html")
        if not os.path.exists(src):
            sys.exit(f"  {folder}/index.html is missing - run build_site.py first")
        html = re_page(open(src, encoding="utf-8").read(), os.path.dirname(src), dest)
        out = os.path.join(DIST, dest, "index.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  dist/{dest + '/' if dest else '':14s} index.html  {len(html):,} B")
        queue += refs(out, DIST, True)

    copied, seen = 0, set()
    # the social share card is never loaded by a page - only named in og: meta - so it is
    # carried by hand, or a link pasted into WhatsApp would point at nothing
    queue += [r for r in ("wp-content/uploads/brand/og-image.jpg",)
              if os.path.isfile(os.path.join(ROOT, r))]
    while queue:
        r = queue.pop()
        if r in seen:
            continue
        seen.add(r)
        src = os.path.join(ROOT, r)
        dst = os.path.join(DIST, r)
        if (not os.path.isfile(src) or r in ("robots.txt", "sitemap.xml", "404.html")
                or os.path.splitext(src)[1] in SKIP_EXT or os.path.basename(src).startswith("index.html")):
            continue
        if os.path.getsize(src) < 8:
            continue                                          # the mirror's empty stub files
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if r.endswith(".css"):
            txt = open(src, encoding="utf-8", errors="ignore").read()

            def keep(m):
                t = resolve(m.group(1), os.path.dirname(src))
                ok = t and os.path.isfile(os.path.join(ROOT, t)) and os.path.getsize(os.path.join(ROOT, t)) > 8
                return m.group(0) if ok else "none"

            txt2 = re.sub(r"""url\(\s*['"]?([^'")]+)['"]?\)""", keep, txt)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(txt2)
        else:
            shutil.copy2(src, dst)
        copied += 1
        if r.endswith((".css", ".js")):
            queue += refs(dst, DIST, False)

    nav = " · ".join(f'<a href="/{d}/">{n}</a>' for d, n in
                     [("about", "About"), ("our-services", "Services"), ("contact-us", "Contact")])
    with open(os.path.join(DIST, "404.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Page not found — Epic Sea Cargo</title>'
                '<style>body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;'
                'background:#013173;color:#fff;display:grid;place-items:center;min-height:100vh;'
                'margin:0;text-align:center;padding:2rem}a{color:#fff}h1{font-size:2rem;margin:0 '
                '.5rem}p{margin:0 0 1rem;opacity:.8}</style></head><body><div>'
                '<h1>Nothing here.</h1><p>That page is gone or mis-typed.</p>'
                f'<p><a href="/">Home</a> · {nav}</p></div></body></html>')
    with open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n\nSitemap: " + SITE + "/sitemap.xml\n")
    with open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org'
                '/schemas/sitemap/0.9">\n')
        for _folder, dest in PAGES:
            f.write(f"  <url><loc>{SITE}/" + (dest + "/" if dest else "") + "</loc></url>\n")
        f.write("</urlset>\n")

    bad = []
    for dirpath, _dirs, files in os.walk(DIST):
        for fn in files:
            p = os.path.join(dirpath, fn)
            if fn.endswith((".html", ".css", ".js")):
                for r in refs(p, DIST, fn.endswith(".html")):
                    q = os.path.join(DIST, r)
                    if not os.path.isfile(q):
                        bad.append(f"{os.path.relpath(p, DIST)} -> {r}")
                    elif os.path.getsize(q) < 8:
                        bad.append(f"{os.path.relpath(p, DIST)} -> {r} (empty)")
    n = sum(len(f) for _d, _x, f in os.walk(DIST))
    mb = sum(os.path.getsize(os.path.join(d, x)) for d, _x, fs in os.walk(DIST) for x in fs) / 1e6
    left = sum(1 for d, _x, fs in os.walk(ROOT) if "/dist" not in d and "/.git" not in d for x in fs) - n
    print(f"  dist/: {n} files · {copied} assets carried · {mb:.2f} MB total")
    print(f"  left behind in the mirror: {left} files no page loads")
    for _folder, dest in PAGES:
        p = os.path.join(DIST, dest, "index.html")
        w = sum(os.path.getsize(os.path.join(DIST, r)) for r in refs(p, DIST, True)
                if os.path.isfile(os.path.join(DIST, r))) + os.path.getsize(p)
        print(f"       /{dest + '/' if dest else '':13s} first load ≈ {w // 1024:,} KB")
    if bad:
        print(f"  ✗ {len(bad)} broken reference(s) inside dist/:")
        for b in sorted(set(bad))[:12]:
            print("     ! " + b)
        sys.exit(1)
    print("  ✓ dist/ is self-contained: every href, src, srcset, icon meta and url() resolves inside it")
    mirror_root()


if __name__ == "__main__":
    main()
