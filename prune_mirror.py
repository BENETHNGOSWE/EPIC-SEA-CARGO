#!/usr/bin/env python3
"""prune_mirror.py - keep only the files that matter, delete the demo bulk that does not.

The repository started life as an HTTrack mirror of a WordPress theme demo: 22 MB, most of it
pages that were never built, WooCommerce storefronts, blog posts, and a few hundred empty stub
files the crawler captured as 0 bytes.

What stays is decided by reading the pages, not by guessing:
  - the four built pages (epic-home, about, our-services, contact-us) and the scripts
  - the mirror pages build_site.py lifts sections from (SOURCES) - without these the builder
    cannot rebuild the site
  - the pages we have talked about building next (FUTURE below)
  - every file any of those reference, followed through CSS and JS to fonts and images
Everything else goes. Dry run by default; --apply deletes and writes prune-removed.txt, and
`git checkout -- .` puts any of it back, because all of it is in history.

  python3 prune_mirror.py            # report only
  python3 prune_mirror.py --apply    # delete
"""
import os, re, sys, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
DRY = "--apply" not in sys.argv

BUILT = ["epic-home", "about", "our-services", "contact-us"]
# what build_site.py reads, kept in step with its SOURCES table
SOURCES = ["home-01/index.html", "home-02/index.html", "home-04/index.html", "about-us/index.html",
           "services/index.html", "contact/index.html"]
# pages we have discussed building: kept so their sections can be lifted later
FUTURE = ["faq", "our-team", "how-we-work", "our-history", "pricing", "service"]
KEEP_FILES = ["build_site.py", "brand_assets.py", "export_site.py", "check_pages.py",
              "serve.py", "prune_mirror.py", "DEPLOY.md",
              "README.md", "robots.txt", "sitemap.xml", ".gitignore", "prune-removed.txt"]
BRAND = "wp-content/uploads/brand"
NEVER = {".git", "dist", "__pycache__", ".arena", ".cache", "node_modules"}

ATTR = re.compile(r"""(?:src|href|poster|imagesrcset|data-src)\s*=\s*["']([^"']+)["']""", re.I)
SRCSET = re.compile(r"""srcset\s*=\s*["']([^"']+)["']""", re.I)
ICON = re.compile(r"""content="([^"]*(?:wp-content|wp-includes)/[^"]*)\"""", re.I)
URLCSS = re.compile(r"""url\(\s*['"]?([^'")]+)""", re.I)
# Only assets are followed. The mirror pages cross-link each other through their demo menus,
# so following .html would drag the whole 22 MB back in through the nav bar.
ASSET_EXT = {".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".ico",
             ".woff", ".woff2", ".ttf", ".otf", ".eot", ".avif"}


def external(u):
    return not u or u.startswith(("#", "mailto:", "tel:", "data:", "javascript:",
                                 "http://", "https://", "//", "/"))


def resolve(u, base):
    if external(u):
        return None
    p = os.path.normpath(os.path.join(base, u.split("?")[0].split("#")[0]))
    r = os.path.relpath(p, ROOT).replace(os.sep, "/")
    return None if r.startswith("..") else r


def closure(start, keep):
    """Follow references until nothing new turns up, the same walk export_site.py does."""
    queue = list(start)
    while queue:
        r = queue.pop()
        if r in keep or not os.path.isfile(os.path.join(ROOT, r)):
            keep.add(r)
            continue
        keep.add(r)
        if not r.endswith((".html", ".css", ".js")):
            continue
        p = os.path.join(ROOT, r)
        txt = open(p, encoding="utf-8", errors="ignore").read()
        base = os.path.dirname(p)
        found = []
        if r.endswith(".html"):
            found += [m.group(1) for m in ATTR.finditer(txt)]
            found += [m.group(1) for m in ICON.finditer(txt)]
            found += [c.strip().split(" ")[0] for m in SRCSET.finditer(txt)
                      for c in m.group(1).split(",")]
        if r.endswith(".css"):
            found += URLCSS.findall(txt)
        for u in found:
            t = resolve(u, base)
            if t and os.path.splitext(t)[1].lower() in ASSET_EXT:
                queue.append(t)
    return keep


def main():
    live = [f"{b}/index.html" for b in BUILT if os.path.isfile(os.path.join(ROOT, b, "index.html"))]
    start = list(SOURCES)
    for f in FUTURE:                                  # a page and its sub-pages, if it has them
        d = os.path.join(ROOT, f)
        if not os.path.isdir(d):
            continue
        for x in [os.path.join(d, "index.html")] + [os.path.join(d, y, "index.html")
                                                    for y in sorted(os.listdir(d))]:
            if os.path.isfile(x):
                start.append(os.path.relpath(x, ROOT).replace(os.sep, "/"))
    keep = closure(live + start, set())
    for f in KEEP_FILES:
        if os.path.isfile(os.path.join(ROOT, f)):
            keep.add(f)
    for d, _x, fs in os.walk(os.path.join(ROOT, BRAND)):
        keep.update(os.path.relpath(os.path.join(d, x), ROOT).replace(os.sep, "/") for x in fs)

    # anything a kept page links to but which is a folder (a page we do not build) is dead
    all_files, size_all = [], 0
    for d, dirs, fs in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in NEVER]
        for x in fs:
            r = os.path.relpath(os.path.join(d, x), ROOT).replace(os.sep, "/")
            all_files.append(r)
            try:
                size_all += os.path.getsize(os.path.join(ROOT, r))
            except OSError:
                pass
    # never touched, whatever the walk decides: the built pages themselves and the brand artwork
    protected = {f"{b}/index.html" for b in BUILT}
    protected |= {r for r in all_files if r.startswith(BRAND + "/")}
    drop = [r for r in all_files if r not in keep and r not in protected]
    size_drop = sum(os.path.getsize(os.path.join(ROOT, r)) for r in drop)
    empty = [r for r in drop if os.path.getsize(os.path.join(ROOT, r)) == 0]
    by_top = collections.Counter(r.split("/")[0] if "/" in r else "(root)" for r in drop)
    by_kind = collections.Counter(os.path.splitext(r)[1] or "(none)" for r in drop)

    print(f"{len(all_files)} files / {size_all/1e6:.1f} MB in the working tree")
    print(f"  keep {len(keep)} · remove {len(drop)} ({size_drop/1e6:.1f} MB), "
          f"of which {len(empty)} are empty stubs")
    print("  biggest things going: " + ", ".join(f"{k} x{v}" for k, v in by_top.most_common(9)))
    print("  by type: " + ", ".join(f"{k} x{v}" for k, v in by_kind.most_common(7)))
    print(f"  kept: {len(live)} built pages · {len(start)} mirror pages the builder reads "
          f"· {len([r for r in keep if r.startswith('wp-content/themes')])} theme files "
          f"· {len([r for r in keep if r.startswith(BRAND)])} brand files")
    if "--list" in sys.argv:
        print("\n  root-level files going: " + (", ".join(r for r in drop if "/" not in r) or "none"))
        areas = collections.Counter("/".join(r.split("/")[:3]) for r in drop if "/" in r)
        print("  removals by area:")
        for k, v in areas.most_common(12):
            print(f"     {k:52s} x{v}")
        print("  theme files kept:")
        for r in sorted(x for x in keep if x.startswith("wp-content/themes"))[:16]:
            print("     " + r.replace("wp-content/themes/frexus/", ""))
        return 0
    if not drop:
        print("  nothing to remove - already pruned")
        return 0
    if DRY:
        print("\n  dry run: nothing deleted. re-run with --apply")
        return 0
    manifest = os.path.join(ROOT, "prune-removed.txt")
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("# removed by prune_mirror.py - every one of these is recoverable with:\n"
                "#   git checkout -- .   (they are all in history)\n" + "\n".join(sorted(drop)) + "\n")
    for r in drop:
        try:
            os.remove(os.path.join(ROOT, r))
        except OSError:
            pass
    for d, dirs, fs in os.walk(ROOT, topdown=False):
        if os.path.basename(d) in NEVER:
            continue
        try:
            if not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass
    print(f"\n  removed {len(drop)} files / {size_drop/1e6:.1f} MB · manifest: prune-removed.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
