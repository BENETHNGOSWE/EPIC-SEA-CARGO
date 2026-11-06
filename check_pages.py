#!/usr/bin/env python3
"""check_pages.py — the audit to run after every build.

Fetches each built page from the preview server, follows every href / src / srcset in the
HTML and every url() inside the stylesheets it loads, and reports anything that answers
404 or 0 bytes. Also prints the section order, the headings, where the nav points, and
any demo debris left in the markup - so a regression shows up here instead of in the
browser.

    python3 serve.py &
    python3 build_site.py && python3 check_pages.py
"""
import os, re, sys, urllib.request, urllib.error
from urllib.parse import urljoin

BASE = "http://127.0.0.1:8090"
PAGES = ["epic-home", "about", "our-services", "contact-us"]

HEADER = re.compile("<header" + "[\\s\\S]*?" + "</header>")
NAVLINK = re.compile("href=[\"'](\\./|\\.\\./[a-z-]+/)[\"']")
# Which pages exist is not something this file should guess: read it from the builder, and
# then any link that resolves to a folder that is not built is a failure - the old hand-written
# list of demo folders is exactly how an href="../pricing/index.html" got through.
_bs = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_site.py"),
           encoding="utf-8").read()
BUILT = set(re.findall(r'^    "([\w-]+)": \{', _bs, re.M)) | {""}


def _link_target(u):
    u = u.split("?")[0].split("#")[0]
    if u.startswith(("http", "#", "mailto", "tel", "data", "//")) or not u:
        return None
    parts = [x for x in u.split("/") if x not in ("", ".", "..")]
    if parts and parts[-1] == "index.html":
        parts.pop()
    elif u.endswith("index.html"):
        parts.pop()
    elif not u.endswith("/"):
        return None                                 # an asset, not a page
    return parts[-1] if parts else ""


def _dangling(html):
    out = set()
    for m in re.finditer(r'''href=["']([^"']+)["']''', html):
        f = _link_target(m.group(1))
        if f is not None and f not in BUILT:
            out.add(f)
    return sorted(out)
SRCISH = re.compile("href=[\"']([^\"']+)[\"']|src=[\"']([^\"']+)[\"']|srcset=[\"']([^\"']+)[\"']")
URLINCSS = re.compile(r"url\([\"']?([^\"')]+)")
CSSRULE = re.compile(r"([^{}]+)\{([^{}]*)\}")          # selector + body, one rule at a time
DEBRIS = ("Frexus", "frexuswp", "New York", "Guild Street", "Since 1980", "25+ years",
          "websitelayout", "yourdomain.com", "cdn-cgi")


def get(u):
    try:
        r = urllib.request.urlopen(u, timeout=40)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, str(e).encode()


def refs_of(html):
    out = set()
    for m in SRCISH.finditer(html):
        for piece in (m.group(1), m.group(2), m.group(3)):
            if not piece:
                continue
            for cand in piece.split(","):
                u = cand.strip().split(" ")[0].split("?")[0].split("#")[0]
                if not u or u.startswith(("http", "//", "mailto:", "tel:", "data:", "javascript:", "#")):
                    continue
                out.add(u)
    return out


def main():
    fails = 0
    for page in PAGES:
        url = "%s/%s/" % (BASE, page)
        st, raw = get(url)
        if st != 200:
            print("%s: HTTP %s — preview server down? (run: python3 serve.py &)" % (page, st))
            return 1
        t = raw.decode("utf-8", "ignore")
        refs = refs_of(t)
        bad, kb = [], len(raw) / 1024
        for u in sorted(refs):
            s, d = get(urljoin(url, u))
            kb += len(d) / 1024
            if s != 200:
                bad.append("%s -> %s" % (u, s))
            elif not d:
                bad.append("EMPTY %s" % u)
            if u.endswith(".css"):
                # A stylesheet can carry rules for containers this page never lifted, and
                # the browser will not fetch an image whose rule matches nothing. So only
                # complain about a url() whose rule actually targets something on the page.
                for mm in CSSRULE.finditer(d.decode("utf-8", "ignore")):
                    sel, body = mm.group(1), mm.group(2)
                    subject = sel.strip().split(",")[-1].split()[-1] if sel.strip() else ""
                    toks = set(re.findall(r"[.#][\w-]+", subject))
                    if toks and not any(tk.lstrip(".#") in t for tk in toks):
                        continue                       # rule's subject is not on this page
                    for am in URLINCSS.finditer(body):
                        a = am.group(1).strip()
                        if a.startswith(("data:", "http", "//")):
                            continue
                        s2, d2 = get(urljoin(urljoin(url, u), a))
                        if s2 != 200:
                            bad.append("%s wants %s -> %s" % (u.split("/")[-1], a, s2))
                        elif not d2:
                            bad.append("%s wants %s (0 bytes)" % (u.split("/")[-1], a))
        order = re.findall("data-elementor-id=\"(\\d+)\"", t)
        heads = [re.sub("<[^>]+>", "", h).strip()
                 for h in re.findall("<h[1-3][^>]*>(.*?)</h[1-3]>", t, re.S)]
        nav = HEADER.search(t).group(0) + re.search(r"<footer[\s\S]*?</footer>", t).group(0)
        navlinks = sorted(set(NAVLINK.findall(nav)))
        demo = [w for w in DEBRIS if w in t]
        print("%-13s 200 · %3d files · %6.0f KB · broken/empty %d" %
              (page, len(refs), kb, len(bad)))
        print("   elementor page-ids, in order: %s" % order)
        print("   headings: %s" % heads[:6])
        print("   nav links to built pages: %s" % navlinks)
        mirror = _dangling(t)
        print("   links still hitting the mirror: %s" % (mirror or "none"))
        if mirror:
            bad.append("a link points at a page that was never built: %s" % mirror[:4])
        if demo:
            print("   DEMO DEBRIS PRESENT: %s" % demo)
        for b in sorted(set(bad))[:8]:
            print("   X %s" % b[:120])
        fails += len(bad) + (1 if demo else 0)
        print()
    print("ALL CLEAN — every subresource of every built page resolves with bytes, no demo debris left"
          if not fails else "%d problem(s) to fix" % fails)
    return 1 if fails else 0


sys.exit(main())
