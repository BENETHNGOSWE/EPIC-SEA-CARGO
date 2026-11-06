#!/usr/bin/env python3
"""
build_site.py — assemble Epic Sea Cargo's static pages out of the mirrored
Frexus demo, reusing the theme's own CSS/JS so every page looks like the demo.
Each page is a list of containers lifted from the demo's own pages, plus the
shared navbar and footer. Add a page = add an entry to PAGES.
  page dir      sections (source page → phrase or #container-id of its Elementor block)
  ---------------------------------------------------------------------------
  epic-home     hero(home-02) · about(home-01) · services(home-02) · process(home-04)
                · why-us(home-02) · contact(home-02)
  about         banner(about-us) · about(home-01) · pricing(services) · contact(services)
  our-services  banner(services) · services grid(services) · process(home-04)
                · contact(services)
  contact-us    banner(about-us, relabelled) · form(home-02) · contact(services)

Folder names avoid the mirror's own services/ and contact/ dirs, which are the build
inputs. To add a page: copy one PAGES entry, list its sections, and add the mirror path
to SOURCES + NAV_MAP. ONLY_BUILT at the top decides whether links to pages that do not
exist yet are trimmed from the menu or left pointing at the mirror.

Everything after the lift is a fix, not decoration — see the STAGES list.
Re-run after editing:  python3 build_site.py
"""
import re, os, sys, glob, html as H, collections, urllib.request, urllib.parse
ROOT    = os.path.dirname(os.path.abspath(__file__))
SITE    = "https://epicseacargo.com"        # canonical, sitemap and og: URLs all hang off this
HOME    = "epic-home"                         # folder of the homepage
# ------------------------------------------------------------------ sources
# key          (file in the mirror,            Elementor page id, folder depth)
SOURCES = {
    "home-01":  ("index.html",           "6085",  0),
    "home-02":  ("home-02/index.html",   "6265",  1),
    "home-04":  ("home-04/index.html",   "29829", 1),
    "about-us": ("about-us/index.html",  "4899",  1),
    "services": ("services/index.html",  "2887",  1),
    "contact":  ("contact/index.html",   "5373",  1),
}
HEADER_FROM, FOOTER_FROM = "home-02", "home-01"
PAGES = {
    "epic-home": {
        "title": "Epic Sea Cargo — Ocean Freight, Customs Clearance &amp; Inland Transport | Dar es Salaam",
        "desc":  "Sea freight in and out of Dar es Salaam: container bookings, customs clearance, inland transport, warehousing. Send the packing list and we quote the whole lane.",
        "sections": [
            ("home-02", "World Wide Shipping",             "hero"),
            ("home-01", "smart logistics solutions",       "about us"),
            ("home-02", "Strategic guidance for business", "services"),
            ("home-04", "Explore Our Process Steps",       "process"),
            ("home-02", "delivering the best customer",    "why choose us"),
            ("home-02", "here to help you",                "contact"),
        ],
    },
    "about": {
        "title": "About Us — Epic Sea Cargo | Ocean Freight &amp; Clearance Desk, Dar es Salaam",
        "desc":  "Who we are: a Dar es Salaam freight desk handling container bookings, documentation, customs clearance coordination, inland transport and storage for importers, exporters and project shippers.",
        "sections": [
            ("about-us", "#30527ef",                            "page banner"),
            ("home-01",  "smart logistics solutions",           "about us"),
            ("services", "Flexible plans for every shipment",   "pricing"),
            ("services", "Ready to move faster",                "contact"),
        ],
        # the demo's three price cards became "what sets the price" - it describes how a
        # quote is built instead of quoting numbers we do not have. If they ever publish a
        # rate card, that is a page of its own, not this block.
        "todo": ("Three things that set the price", "no prices on the site yet by design"),
    },
    "our-services": {
        "title": "Our Services — Ocean Freight, Clearance, Transport &amp; Storage | Epic Sea Cargo",
        "desc":  "FCL and LCL ocean freight, customs clearance at the Port of Dar es Salaam, inland haulage, warehousing, project and breakbulk cargo, reefer - with documentation and marine insurance arranged on request.",
        "sections": [
            ("services", "#f152730",                              "page banner"),
            ("services", "Smart transport and logistics solution", "services grid"),
            ("home-04",  "Explore Our Process Steps",              "process"),
            ("services", "Ready to move faster",                   "contact"),
        ],
    },
    "contact-us": {
        "title": "Contact Us — Epic Sea Cargo | Masasi Street, Dar es Salaam",
        "desc":  "Send the shipment details to info@epicseacargo.com and we will quote the lane: ocean freight, customs clearance, inland transport and storage from Dar es Salaam.",
        "banner_text": "Contact Us",
        # NB the demo contact page's own stylesheet (post-5373) came back from the mirror
        # as a 0-byte stub, so its "Get in touch" block would render unstyled. Same form,
        # same fields, but lifted from home-02 where the CSS does exist.
        "sections": [
            ("about-us", "#30527ef",       "page banner"),
            ("home-02",  "here to help you", "form + address"),
            ("services", "Ready to move faster", "contact"),
        ],
    },
}
# Everything below is either a fact Epic Sea Cargo gave us or a placeholder they told us to
# leave until they confirm it. Nothing here is invented: no founding year, no client counts,
# no "24/7", no rate promises.
EMAIL_PLACE = "info@epicseacargo.com"         # supplied - quotes, form delivery, footer
PHONE_PLACE = "+255 700 000 000"             # NOT supplied yet: they will send numbers
PHONE = ""                                   # put the real number here, e.g. "+255 7XX XXX XXX"
SOCIAL = {}                                  # {"facebook": "https://…", "linkedin": "https://…"}
# While PHONE is blank the number is printed but not dialable, and the footer's social row is
# left off entirely: a tel: link that dials nothing and four grey icons that go nowhere are
# worse than no row at all. Both come back the moment you fill the value in.
ADDRESS = "Masasi Street, Ndanda St, Dar es Salaam"
MAPS = ("https://www.google.com/maps/search/?api=1&query="
        "Masasi%20Street%2C%20Ndanda%20St%2C%20Dar%20es%20Salaam")
FACT_BLURB = ("Ocean freight, customs clearance, inland transport and storage out of Dar es "
              "Salaam - booking, documentation and delivery handled on one file.")
COPY_USED = set()      # which copy pairs actually fired; checked once at the end of the run
# Anything the theme demo says about itself that is not ours to say. Applied to every
# page, so a claim can never survive by hiding in a section nobody thought about.
FORBIDDEN = ["Frexus", "frexuswp", "websitelayout", "New York", "Guild Street", "Since 1980",
             "+44", "1234567890", "25+ years", "@yourdomain.com", "@example.com",
             "most trusted transport partner",
             # the demo was a global air/sea/road template; we are a sea-freight desk in Dar es
             # Salaam, so none of its wording - or its placeholders - may survive to a built page
             "Air Freight", "Air freight", "air freight", "by air", "Air, sea", "Air, Sea",
             "World Wide Shipping", "Trusted User", "Award Winner", "Basic Plan", "Business Plan",
             "Professional Plan", "www.example.com", "Our Newsletter", "Fax Id", "Global Leaders",
             "Real-Time Tracking", "Worldwide Service", "Quality Control System", "Select Invoice",
             "tracking number", "online portal", "TODO@", "your-domain.example",
             "$ 00.00", "24/7 Support", "Get Started"]
DEMO = {
    r'\+1234567890':             PHONE_PLACE,
    r'\(\+123\)\s*456\s*7890': PHONE_PLACE,
    r'\(\+44\)\s*123\s*456\s*789': PHONE_PLACE,
    r'\(\+44\)\s*152-567-987':     PHONE_PLACE,
    r'addyour@emailhere':        EMAIL_PLACE,
    r'addyour@email':            EMAIL_PLACE,
    r'info@domain\.com':         EMAIL_PLACE,
    r'support@domain\.com':      EMAIL_PLACE,
    r'example@gmail\.com':       EMAIL_PLACE,
    r'\[email(?:&#160;| )protected\]': EMAIL_PLACE,
    r'66 Guild Street 512B, Great North Town\.': ADDRESS,
    r'\bNew York\b':            "Dar es Salaam",
    r'\bSince 1980\b':          "Dar es Salaam",
    r'We have been the most trusted transport partner for 25\+ years\.': FACT_BLURB,
}
MENU_DROP = {
    "Home 01 \u2013 Video", "Home 02", "Home 03 \u2013 Dark Menu", "Home 04",
    "Our Pricing", "Shop", "Our Products", "Single Product", "Cart", "Checkout",
    "Others", "Coming Soon", "Error 404", "Privacy Policy", "Terms & Conditions",
    "Portfolio", "Portfolio Grid", "2 Columns", "3 Columns \u2013 Standard", "4 Columns",
    "Portfolio Details", "Blog", "Blog Default", "Blog Grid", "2 Col \u2013 Left Sidebar",
    "2 Col \u2013 Right Sidebar", "Blog Details",
}
MENU_RENAME = {"Pages": "Company", "FAQ&#039;s": "FAQ", "FAQ’s": "FAQ"}
CSS_DROP_ALWAYS = {"woocommerce-layout", "woocommerce-smallscreen", "woocommerce-general"}
JS_DROP_IF = {"woocommerce": "woocommerce", "photoswipe": "data-lg-src",
              "lightgallery": "data-lg-src", "magnific": "mfp-", "gw-layout": "elementor-gf"}
# A nav link to a page we have not built would 404 on the live host, so menu items whose
# target is not one of our pages are dropped. Flip this to False and the demo links stay,
# which is what you want once I have built FAQ / Our Team / Our History / How We Work too.
ONLY_BUILT = True
# In-page buttons ("Read More" under a service card, say) that were wired to a demo page
# we never built get re-pointed at the closest real one instead of 404ing.
FALLBACK_LINKS = {"how-we-work": "our-services", "our-team": "about", "our-history": "about",
                  "faq": "about", "service": "our-services", "project": "epic-home",
                  "shop": "epic-home", "blog": "epic-home", "portfolio": "epic-home"}
NAV_MAP = {  # mirror page → folder we build it in
    "index.html": HOME, "../index.html": HOME,
    "../about-us/index.html": "about", "about-us/index.html": "about",
    "../services/index.html": "our-services", "services/index.html": "our-services",
    "../contact/index.html": "contact-us", "contact/index.html": "contact-us",
}
STAGES = ("lift → menu → contact → weight → deps → demo-wiring → fonts/images/forms "
          "→ brand/rates → guard")
# the mirror's 0-byte stubs: the theme asks for these, HTTrack never fetched them
FA_DIR  = "wp-content/themes/frexus/assets/fonts"
FA_BASE = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/webfonts"
FA_WOFF2 = ["fa-brands-400.woff2", "fa-regular-400.woff2", "fa-solid-900.woff2",
            "fa-v4compatibility.woff2"]
# Same story for the other icon set the theme uses (`ti-*` in the topbar and the slider
# arrows): themify-icons.css is intact, its font files were not mirrored. The public
# Themify Icons set was checked against the theme's CSS - all 351 classes, identical
# codepoints - so restoring these two files brings the glyphs back.
ICON_BASE = "https://cdn.jsdelivr.net/gh/lykmapipo/themify-icons@master/fonts"
ICON_FILES = ["themify.woff", "themify.ttf"]
THEMIFY_CSS = "wp-content/themes/frexus/assets/css/plugins/themify-icons.css"
BRAND = "Epic Sea Cargo"
BRAND_DIR = "wp-content/uploads/brand"          # logo source + everything derived from it
BRAND_SRC = "wp-content/uploads/brand/epic-sea-cargo.jpg"
# The Frexus demo is painted with an orange accent (#EB4304) and a teal-navy (#003751).
# Their artwork is navy #013173 and crimson #A3002B, so the accent becomes the crimson and
# every navy surface becomes the navy from the logo. Hover states keep their lighter step.
BRAND_MAP = {"#EB4304": "#A3002B", "#F5543F": "#C4163C", "#003751": "#013173",
             "#6EC1E4": "#013173", "#61CE70": "#A3002B"}     # the demo kit's placeholder globals
# Which file to use, and how tall to show it: desktop, laptop, phone. The theme sizes the
# header logo for its own artwork (.navbar-brand img max-height:63px), which squashed a mark
# with a taller ratio, so brand.css is generated from these numbers - change the logo size
# here and nowhere else.
BRAND_LOGOS = {
    "header": ("logo.webp", 68, 54, 44),
    "footer": ("logo-footer.webp", 96, 96, 76),   # inside .footer-logo, capped at 215px wide
}
# ------------------------------------------------------------------ helpers
def read(key):
    rel, pid, depth = SOURCES[key]
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as f:
        return f.read(), pid, depth
def balanced(s, start, tag="div"):
    d = 0
    for m in re.finditer(rf"<{tag}\b|</{tag}>", s[start:], re.I):
        d += 1 if m.group(0).lower().startswith(f"<{tag}") else -1
        if d == 0:
            return start + m.end()
    return len(s)
def containers(s):
    out = []
    for m in re.finditer(r'<div[^>]*class="[^"]*\be-parent\b[^"]*"[^>]*data-id="([0-9a-f]+)"', s):
        st = m.start() if s.startswith("<div", m.start()) else s.rfind("<div", 0, m.start())
        out.append((m.group(1), s[st:balanced(s, st)]))
    return out
def plain(b):
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b)))
def normlab(t):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")).strip()
def pick(conts, phrase, label):
    """Find the container for a section. `phrase` is matched against the container's
    visible text (Elementor ids are not stable across demo pages), with two escapes:
    '#id' selects that container id exactly, '~phrase' selects the SMALLEST container
    holding the phrase - useful when the words also appear in the demo footer block."""
    if phrase.startswith("#"):
        did = phrase[1:]
        hit = [(len(b), i, b) for i, b in conts if i == did]
        if not hit:
            raise SystemExit(f"  ✗ no container #{did} on that page ({label})")
    else:
        want, txt = (phrase[1:].lower(), True) if phrase.startswith("~") else (phrase.lower(), False)
        hit = [(len(b), did, b) for did, b in conts if want in plain(b).lower()]
        if not hit:
            raise SystemExit(f"  ✗ nothing matches {phrase!r} for {label}")
        hit.sort()
    n, did, b = hit[0] if phrase.startswith("~") else hit[-1]
    return did, n, b
def rebase(frag, src_depth, dst_depth=1):
    if src_depth == dst_depth:
        return frag
    delta = dst_depth - src_depth
    EXT = ("http:", "https:", "//", "#", "mailto:", "tel:", "data:", "javascript:", "sms:")
    def shift(u):
        if u.startswith(EXT) or u.startswith("?"):
            return u
        if delta > 0:
            return "../" * delta + u
        lead = "../" * (-delta)
        return u[len(lead):] if u.startswith(lead) else u
    frag = re.sub(r'\b(href|src|poster|action|data-src|data-lazy-src)\s*=\s*(["\'])([^"\']*)\2',
                  lambda m: f'{m.group(1)}={m.group(2)}{shift(m.group(3))}{m.group(2)}', frag)
    # srcset is a comma-separated list of "url 696w" pairs, so the href|src pass above
    # never touches it. A stale srcset silently replaces the (correctly shifted) src with
    # a 404 - which is exactly what "the images are arranged wrong" looks like.
    def setfix(m):
        parts = []
        for cand in m.group(3).split(","):
            bits = cand.strip().split(" ", 1)
            if not bits[0]:
                continue
            parts.append(shift(bits[0]) + (" " + bits[1] if len(bits) > 1 else ""))
        return f'{m.group(1)}={m.group(2)}{", ".join(parts)}{m.group(2)}'
    frag = re.sub(r'\b(srcset|imagesrcset)\s*=\s*(["\'])([^"\']+)\2', setfix, frag)
    return re.sub(r'url\(\s*(["\']?)([^)\s"\']+)\1\s*\)',
                  lambda m: f'url({m.group(1)}{shift(m.group(2))}{m.group(1)})', frag)
def css_is_live(href, outdir):
    """True when the stylesheet is really there. HTTrack saved several of these as 0-byte
    .html stubs, and a <link> to one is a wasted request that styles nothing."""
    f = os.path.normpath(os.path.join(outdir, href.split("?")[0]))
    if f.startswith(ROOT) is False:
        f = os.path.normpath(os.path.join(ROOT, os.path.relpath(f, outdir)))
    return os.path.exists(f) and os.path.getsize(f) > 512
def drop_dead_css(html_txt, outdir, log=True):
    """Remove <link> tags whose stylesheet is 0-byte or absent (see css_is_live)."""
    dead = []
    def keep(m):
        tag = m.group(0)
        hm = re.search(r"""href=['"]([^'"]+\.css)['"]""", tag)
        if hm and not css_is_live(hm.group(1), outdir):
            dead.append(hm.group(1).split("/")[-1])
            return ""
        return tag
    out = re.sub("""<link[^>]*rel=['"]stylesheet['"][^>]*>""", keep, html_txt)
    if dead and log:
        print(f"  weight: {len(dead)} stylesheet(s) not linked (0-byte in the mirror): "
              f"{', '.join(dead[:4])}{' …' if len(dead) > 4 else ''}")
    return out
def elementor_css(page_html):
    return re.findall(r"<link rel='stylesheet'[^>]*href='([^']*uploads/elementor/css/post-[^']*)'", page_html)
# ------------------------------------------------------------------ stages
def _folder_of(href):
    """'../about-us/index.html' and 'about-us/index.html' both mean the folder
    'about-us'; the repo root is ''."""
    u = href.split("?")[0].split("#")[0].rstrip("/")
    if not u.endswith("index.html"):
        return None
    parts = [x for x in u.split("/") if x not in ("", ".", "..", "index.html")]
    return parts[-1] if parts else ""        # "../index.html" and "index.html" are both the root
BUILT_FOLDERS = {f for f in PAGES} | {_folder_of(k) for k in NAV_MAP} - {None}
def tidy_parents(frag):
    """A menu parent whose children have all been removed must lose its caret class and
    its empty panel - but only that one. Stripping `dropdown` everywhere would kill the
    hover and the mobile toggle on the groups that still have items."""
    frag = re.sub(r"""<ul class="(?:sub-menu|dropdown-menu)[^"]*"[^>]*>\s*</ul>""", "", frag)
    out, pos = [], 0
    for m in re.finditer(r"<li\b[^>]*>", frag):
        en = balanced(frag, m.start(), "li")
        if "<ul" in frag[m.end():en]:
            continue                                  # still has a panel: leave it alone
        cls = re.search(r'class="([^"]*)"', m.group(0))
        if not cls:
            continue
        new = re.sub(r"\s*(?:menu-item-has-children|dropdown)\b", "", cls.group(1)).strip()
        if new != cls.group(1).strip():
            # keep the item's own body - only its class list changes
            out.append(frag[pos:m.start()] +
                       m.group(0).replace(cls.group(0), f'class="{new}"') + frag[m.end():en])
            pos = en
    return "".join(out) + frag[pos:] if out else frag

def drop_unbuilt(frag):
    """Remove menu entries that point at a mirror page we never built."""
    gone = []
    for _ in range(120):
        hit = None
        for cand in re.finditer(r"<li\b[^>]*>", frag):
            st, en = cand.start(), balanced(frag, cand.start(), "li")
            block = frag[st:en]
            links = re.findall(r'''<a\b[^>]*href="([^"]*)"''', block)
            if not links:
                continue
            # only real page links count as evidence: a dropdown parent is allowed to sit
            # on "#" (that is how WP marks a parent), and "Home" gets its href rewritten to
            # the homepage a few lines later
            pages = [u for u in links if _folder_of(u) is not None]
            bad = [u for u in pages if _folder_of(u) not in BUILT_FOLDERS]
            if pages and len(bad) == len(pages):
                a = re.search(r"<a\b[^>]*>([\s\S]*?)</a>", block)
                label = normlab(a.group(1)) if a else ""
                segs = bad[0].split("/")
                hit = (st, en, label or (segs[-2] if len(segs) > 1 else "home"))
                break
        if not hit:
            break
        st, en, label = hit
        frag = frag[:st] + frag[en:]
        gone.append(label)
    frag = tidy_parents(frag)
    return frag, gone
# The menu, flat. label -> folder built by PAGES. Empty list = keep the demo's own
# (dropdown) menu, only minus the entries that point at pages we never built.
NAV_ITEMS = [("Home", HOME), ("About Us", "about"), ("Services", "our-services"),
             ("Contact", "contact-us")]


def rebuild_nav(header, folder):
    """Replace the demo's hover menu with a flat list of the real pages. The <li>/<a> markup
    and the classes are the theme's own, so the styling, the active-item colour and the
    mobile toggler all behave exactly as they did with four items instead of a dropdown."""
    i = header.find('<ul id="nav"')
    if i < 0:
        return header, []
    j = balanced(header, i, "ul")
    open_tag = header[i:header.find(">", i) + 1]
    items = []
    for label, target in NAV_ITEMS:
        href = "./" if target == folder else f"../{target}/"
        cur = " current-menu-item active" if target == folder else ""
        items.append('<li itemscope="itemscope" '
                     'itemtype="https://www.schema.org/SiteNavigationElement" '
                     'class="menu-item menu-item-type-post_type menu-item-object-page'
                     + cur + ' nav-item">'
                     f'<a title="{label}" href="{href}" class="nav-link">{label}</a></li>')
    return header[:i] + open_tag + "\n" + "\n".join(items) + "\n</ul>" + header[j:], [l for l, _ in NAV_ITEMS]

def trim_menu(frag):
    gone = []
    for _ in range(80):
        hit = None
        for cand in re.finditer(r"<li\b[^>]*>", frag):
            st = cand.start(); en = balanced(frag, st, "li")
            a = re.search(r"<a\b[^>]*>([\s\S]*?)</a>", frag[st:en])
            if not a:
                continue
            if normlab(a.group(1)) in {normlab(x) for x in MENU_DROP}:
                hit = (st, en, normlab(a.group(1))); break
        if not hit:
            break
        st, en, label = hit
        frag = frag[:st] + frag[en:]
        gone.append(label)
    # "Home" is the one item we always want, and in the demo it is a dropdown parent whose
    # own href is "#" - give it the real home path before anything judges it as debris.
    frag = re.sub(r'(<a\b[^>]*?)href="#"([^>]*>\s*(?:<span[^>]*>\s*)?Home\s*(?:</span>\s*)?</a>)',
                  lambda m: m.group(1) + 'href="@HOME@"' + m.group(2), frag, count=1)
    if ONLY_BUILT:
        # only the real menu, never the topbar list or the search/cart widgets beside it
        i = frag.find('<ul id="nav"')
        if i >= 0:
            j = balanced(frag, i, "ul")
            inner, extra = drop_unbuilt(frag[i:j])
            frag = frag[:i] + inner + frag[j:]
            gone += extra
    for old, new in MENU_RENAME.items():
        frag = frag.replace(f">{old}</a>", f">{new}</a>")
    # a parent whose children have all gone must not keep its caret or its empty panel
    frag = tidy_parents(frag)
    return frag, gone
def cfemail_decode(s):
    def one(m):
        hexs = next((g for g in reversed(m.groups()) if g), "")
        b = bytes.fromhex(hexs)
        addr = "".join(chr(c ^ b[0]) for c in b[1:])
        return f'<a href="mailto:{addr}">{addr}</a>'
    n = len(re.findall(r'data-cfemail="([0-9a-f]+)"', s))
    s = re.sub(r'<a[^>]*href="[^"]*email-protection[^"]*"[^>]*>\s*'
               r'(<span[^>]*data-cfemail="([0-9a-f]+)"[^>]*>[\s\S]*?</span>)\s*</a>', one, s)
    s = re.sub(r'<span[^>]*class="[^"]*__cf_email__[^"]*"[^>]*data-cfemail="([0-9a-f]+)"[^>]*>[\s\S]*?</span>', one, s)
    s = re.sub(r'<script[^>]*email-decode[^>]*></script>', "", s)
    return s, n
def cfemail_hash(s):
    """Cloudflare also protects plain links: href=".../email-protection#HEX". The hash is
    the address, XOR-keyed by its own first byte. Decode it into href + label, because
    email-decode.min.js is not part of the mirror and the link would be dead."""
    def rep(m):
        pre, url, mid, body, post = m.groups()
        if "email-protection" not in url or "#" not in url:
            return m.group(0)
        try:
            b = bytes.fromhex(url.rsplit("#", 1)[1])
        except ValueError:
            return m.group(0)
        addr = "".join(chr(c ^ b[0]) for c in b[1:])
        if "@" not in addr:
            return m.group(0)
        if re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", body):
            body = re.sub(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", addr, body)
        elif "<i" in body:
            body = re.sub(r"(</i>)[\s]*$", lambda x: x.group(1) + " " + addr + " ", body)
        else:
            body = addr
        return f'{pre}mailto:{addr}"{mid}{body}{post}'
    out, n = re.subn(r'(<a\b[^>]*href=")([^"]*)("[^>]*>)([\s\S]*?)(</a>)', rep, s)
    return out
# ----------------------------------------------------------------- content: what the site says
# The demo cards, refilled. Each list reuses the images its own section already used, so no
# card ends up with a picture cropped into the wrong box. A service is added by adding a row:
# the builder clones the card markup it already has.
IMG_LAND = "../wp-content/uploads/2025/10/"
IMG_TALL = "../wp-content/uploads/2025/09/"
SERVICE_GRID = [                      # our-services: title over a photo, 3 across
    ("Ocean Freight (FCL &amp; LCL)", "service-09.webp"),
    ("Customs Clearance", "service-10.webp"),
    ("Inland Road Transport", "service-11.webp"),
    ("Warehousing &amp; Storage", "service-12.webp"),
    ("Project &amp; Breakbulk Cargo", "service-13.webp"),
    ("Reefer &amp; Temperature-Controlled", "service-14.webp"),
]
HOME_SERVICES = [                     # home carousel: title + one line, portrait image
    ("Ocean Freight", "Full &amp; shared containers", "service-05.webp"),
    ("Customs Clearance", "Port of Dar es Salaam", "service-06.webp"),
    ("Inland Transport", "Quayside to your door", "service-07.webp"),
    ("Warehousing &amp; Storage", "Short &amp; long term", "service-08.webp"),
]
# Services that are real but do not warrant a card: they get one honest line under the grid.
SERVICE_ALSO = ("Also: relief and transshipment cargo, documentation and booking support, "
                "marine insurance arranged on request, and survey or claim handling when "
                "something goes wrong.")
STAT_TILES = [("FCL", "Full container loads, booked with the line", "Container loads"),
              ("LCL", "Shared containers, consolidated for you", "Groupage")]

# (what the demo page says, what we say). A key ending in an ellipsis swallows the rest of that
# text run, which is how a paragraph we have only seen truncated still gets replaced whole.
# Anything that matches nothing on any page is reported when the build finishes.
COPY = [
    # hero
    ("World Wide Shipping &amp; Fast Solutions.", "Sea Freight, Cleared &amp; Delivered."),
    ("<li>Quality Control System</li><li>Highly Professional Staff</li><li>24/7 Support</li>",
     "<li>Port of Dar es Salaam</li><li>Import · Export · Transit</li><li>FCL · LCL · Breakbulk</li>"),
    # the about block and its three numbered points
    ("Reliable transport smart logistics solutions", "Cargo through Dar es Salaam, handled end to end"),
    ("Real-Time Tracking", "Booking &amp; Stowage"),
    ("Real-time tracking is a technology used in transport and logistics to monitor the location "
     "and status of goods vehicles.",
     "Send the packing list and we quote the lane, book the container with the shipping line and "
     "confirm the schedule, so the plan is settled before anything moves."),
    ("Global Leaders", "Clearance &amp; Documents"),
    ("Global leaders in transport and logistics are companies…",
     "Declarations, duty and tax computation, permits and inspection coordination at the port, all "
     "carried on one file and checked before they are needed."),
    ("Worldwide Service", "Transport &amp; Storage"),
    ("Worldwide service in transport and logistics refers to the ability of companies",
     "Haulage from the quayside to your store or site, upcountry and along the transit corridors, "
     "with storage and consolidation when the cargo has to wait."),
    # services sections
    ("Strategic guidance for business impact.", "What we do, end to end."),
    ("Smart transport and logistics solutions", "Six services, one file"),
    # process
    ("Explore Our Process Steps", "How a shipment runs"),
    ("Our streamlined process ensures every step of your transport and logistics journey…",
     "Every shipment runs the same three steps: we book it, we clear it, we deliver it. One desk "
     "handles all three, so the stages are never chasing each other."),
    ("Select Freight", "Enquiry &amp; Booking"),
    ("Choose from a range of freight options tailored to your needs, including ground, air, and sea transport.",
     "Origin, destination, incoterm, weight and dimensions. We price the whole lane - ocean freight, "
     "clearance, transport and storage - and book with the line."),
    ("Select Invoice", "Documents &amp; Clearance"),
    ("Access and manage your invoices with ease through our…",
     "Commercial invoice, packing list, bill of lading and declarations prepared and checked; duty "
     "and taxes computed; permits and inspection coordination handled at the port."),
    ("Fast Delivered", "Delivery &amp; Storage"),
    ("We ensure your shipments are fast delivered with speed and accuracy, helping you meet tight deadlines.",
     "Haulage from the quayside, offloading at your store or site, storage if the cargo needs to sit, "
     "and a signed delivery note back on the file."),
    # why us, and the one bar that sat under it
    ("We’re delivering the best customer.", "One desk, from enquiry to delivery."),
    ("We offer a complete range of transport and logistics solutions tailored to meet your unique needs…",
     "Booking, documents, clearance, transport and storage are handled by the same desk. You send the "
     "details once, and you always know which stage the cargo has reached."),
    ("On-Time Delivery", "Booking · Clearance · Transport · Storage"),
    ("<div class=\"col-6 text-end\">—</div>", "<div class=\"col-6 text-end\">&nbsp;</div>"),
    # the three questions a shipper actually asks us
    ("1. What types of transport services do you offer?", "1. What do you need to give me a quote?"),
    ("We provide comprehensive transport and logistics solutions…",
     "A packing list or commercial invoice, the incoterm, where the cargo is coming from and where it "
     "is going, and the weight and dimensions. Out-of-gauge, reefer or hazardous - say so at the "
     "start, because it changes the stowage and the price."),
    ("2. How does your shipping process work?", "2. Do you handle clearance as well as the booking?"),
    ("Our process starts with understanding your shipping requirements…",
     "Yes. The booking, the declarations, the duty computation, the permits and the inspection "
     "coordination travel on the same file as your transport, so nothing is handed over halfway."),
    ("3. How can I track my shipment?", "3. Can you move cargo upcountry and to the corridors?"),
    ("We offer real-time shipment tracking through our online portal…",
     "Yes. Container and breakbulk haulage from the Port of Dar es Salaam to destinations across "
     "Tanzania, and relief cargo for Zambia, the DRC, Rwanda, Burundi and Malawi, with the transit "
     "documents prepared with you."),
    # call to action, and the price cards turned into how a quote is built
    ("Get your free industrial transport quote!", "Get a freight quote - send us the packing list."),
    ("Flexible Pricing", "Getting a quote"),
    ("Flexible plans for every shipment", "Three things that set the price"),
    ("Dynamic pricing models help logistics companies adapt…",
     "Every shipment is priced on its own merits. Send the details and you get one figure for the "
     "lane you actually need, and a note of what is not in it."),
    ("&#8211; Epic Sea Cargo got you covered.",
     "&#8211; send us the packing list and we will price it."),
    ("Basic Plan</button>", "The cargo</button>"),
    ("The Basic Plan offers standard support, limited shipments, and access to our transport track dashboard.",
     "Weight, volume, dimensions and how it is packed. Bags, steel, machinery and household goods "
     "each want different handling, and that is where the cost is decided."),
    ("Business Plan</button>", "The route</button>"),
    ("Perfect for businesses scaling their logistics operations with enhanced tools and dedicated account support.",
     "Origin, destination and incoterm. Port-to-port, door-to-door or clearance only are quoted "
     "differently, and we will tell you which one you are buying."),
    ("Professional Plan</button>", "The timing</button>"),
    ("Built for enterprises, the Professional Plan provides end-to-end logistics and real-time performance insights.",
     "When the cargo is ready and which vessel you want. That fixes the booking window, and how much "
     "free time at the port you need to plan for."),
    (">$ 00.00 / Monthly</h5>", ">Every lane priced separately</h5>"),
    ("Get started", "Ask for a quote"),
    (">Get Started</a>", ">Get a Quote</a>"),
    # the contact tiles, in the order the demo lists them
    ("Main Phone Number", "Call the office"),
    ("Training for Success", "Email the quote desk"),
    ("Please visit the training section", "EMAIL"),
    ("For Support Related", "Visit the office"),
    ("Please visit the our faq&#039;s", "ADDRESS"),
    ("For Website Related", "What we handle"),
    ("www.example.com", "Ocean freight · clearance · transport · storage"),
    ("Email Address", "Write to us"),
    ("Find our Locations", "On the map"),
    ("Search on the map", "Masasi Street, Ndanda St"),
    # sections that described the wrong business entirely
    ("Any questions? We are here to help you!", "Any questions about a shipment? Ask us."),
    ("Ready to move faster? Contact us today", "Ready to move? Send the details"),
    ("Reach out to us for support, collaborations, or to learn more about our profession.",
     "Send the cargo details and we will come back with the cost, the documents needed and the schedule."),
    ("Interested in working with us?", "Want a rate for a shipment?"),
]


def tag_extent(h, i, tag="div"):
    """Index just past the element that opens at i, by counting tags of the same name."""
    depth = 0
    for m in re.finditer("</" + tag + r"\b[^>]*>|<" + tag + r"\b[^>]*>", h[i:], re.I):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth == 0:
            return i + m.end()
    return -1


def drop_widget_containing(h, marker):
    """Remove the Elementor widget holding `marker`: how a demo block leaves the site without
    anyone hand-editing a built page."""
    i = h.find(marker)
    if i < 0:
        return h, False
    j = h.rfind('<div class="elementor-element elementor-element-', 0, i)
    if j < 0:
        return h, False
    k = tag_extent(h, j)
    return (h[:j] + h[k:], True) if k > 0 else (h, False)


def _pat(key):
    """The mirror's markup puts newlines and tabs wherever the text looks continuous, so a
    word-by-word pattern with \\s+ between the words is the only way to match it reliably."""
    pat = r"\s+".join(re.escape(w) for w in key.strip().split())
    # tags that my key has touching may sit on separate lines in the mirror
    return pat.replace("><", r">\s*<").replace("</", r"\s*</")


def apply_copy(out, used):
    for key, new in COPY:
        new = new.replace("EMAIL", EMAIL_PLACE).replace("ADDRESS", ADDRESS)
        # new is passed through a lambda so a $ or \ in our copy stays literal text
        if key.endswith(chr(8230)):                       # swallow the rest of the text run too
            out, k = re.subn(_pat(key[:-1]) + "[^<]*", lambda m, n=new: n, out)
        else:
            out, k = re.subn(_pat(key), lambda m, n=new: n, out)
        if k:
            used.add(key)
    return out


def service_cards(out, folder):
    if folder == "our-services":
        i = out.find('<div class="row mt-n4">')
        if i < 0:
            return out, 0
        first = out.find('<div class="col-md-6 col-lg-4', i)
        tpl = out[first:tag_extent(out, first)]
        row_end = tag_extent(out, i) - len("</div>")
        cards = []
        for j, (title, img) in enumerate(SERVICE_GRID):
            plain = title.replace("&amp;", "&")
            c = re.sub(r'src="[^"]*"', 'src="' + IMG_LAND + img + '"', tpl, count=1)
            c = re.sub(r'alt="[^"]*"', 'alt="' + plain + '"', c, count=1)
            c = re.sub(r'(<h3 class="mb-0 h5">)(.*?)(</h3>)',
                       lambda m: m.group(1) + '<a href="../contact-us/" title="' + plain + '">'
                                  + title + "</a>" + m.group(3), c, flags=re.S)
            c = re.sub(r'data-wow-delay="\d+ms"', 'data-wow-delay="' + str(100 + 50 * j) + 'ms"', c)
            cards.append(c)
        out = out[:i + len('<div class="row mt-n4">')] + "".join(cards) + out[row_end:]
        # one line for the services that are real but do not need a card
        out = out.replace('Smart transport and logistics solutions<span class="text-primary">.</span></h2>',
                          'Smart transport and logistics solutions<span class="text-primary">.</span></h2>'
                          '<p class="mb-0 mt-3 text-white opacity8">' + SERVICE_ALSO + "</p>", 1)
        return out, len(cards)
    if folder == HOME:
        starts = [m.start() for m in re.finditer('<div class="service-item', out)]
        if len(starts) < 2:
            return out, 0
        ext = [(a, tag_extent(out, a)) for a in starts]
        items = [out[a:b] for a, b in ext]
        new = []
        for j, (title, sub, img) in enumerate(HOME_SERVICES):
            plain = title.replace("&amp;", "&")
            c = items[min(j, len(items) - 1)]
            c = re.sub(r'src="[^"]*"', 'src="' + IMG_TALL + img + '"', c, count=1)
            c = re.sub(r'alt="[^"]*"', 'alt="' + plain + '"', c, count=1)
            c = re.sub(r'(<h4><a[^>]*>)(.*?)(</a>)', lambda m: m.group(1) + title + m.group(3),
                       c, flags=re.S)
            c = c.replace("<span>Category</span>", "<span>" + sub + "</span>")
            new.append(c)
        return out[:ext[0][0]] + "".join(new) + out[ext[-1][1]:], len(new)
    return out, 0


def static_stats(out):
    """The theme paints these two tiles as counters that animate up to a number. We have no
    numbers worth animating, and making them up is not on the table - so they say what we
    carry instead, and the counter class goes so the script leaves them alone."""
    n = 0
    for i, (word, line, alt) in enumerate(STAT_TILES):
        out, k = re.subn(r'<div class="display-23[^"]*">\s*<div class="odometer[^"]*"[^>]*>[^<]*</div>'
                         r'\s*[+\w]?\s*</div>\s*<p class="mb-0 text-white opacity9">[^<]*</p>',
                         '<div class="display-23 text-white mb-0 font-weight-900">' + word + "</div>"
                         '<p class="mb-0 text-white opacity9">' + line + "</p>", out, count=1)
        n += k
        # the demo's own labels sit on the icon too
        for probe in ("Trusted User", "Award Winner"):
            if probe in out:
                out = out.replace(f'alt="{probe}"', f'alt="{alt}"', 1)
    return out, n


def fix_links(out):
    """Dead demo links in the contact tiles, and the hero button that pointed at About."""
    for dead in ("Please visit the our faq&#039;s", "www.example.com", "Please visit the training section"):
        out = out.replace('<a href="#">' + dead + "</a>", "<span>" + dead + "</span>")
    out = out.replace('<a href="#">Search on the map</a>',
                      '<a href="' + MAPS + '" target="_blank" rel="noopener">Search on the map</a>')
    digits = lambda n: re.sub(r"\D", "", n)
    pat = (r'<a href="#"[^>]*>(\s*)' + r"\s+".join(map(re.escape, PHONE_PLACE.split()))
           + r"(\s*)</a>")
    if PHONE:
        out = re.sub(pat, lambda m: '<a href="tel:' + digits(PHONE) + '">' + m.group(1) + PHONE
                     + m.group(2) + "</a>", out)
    else:                       # placeholder: show it, but do not let anyone dial it
        out = re.sub(pat, lambda m: "<span>" + m.group(1) + PHONE_PLACE + m.group(2) + "</span>", out)
        # the top bar wraps its number in an icon, so that anchor holds markup, not text
        out = re.sub(r'<a href="tel:\+?' + digits(PHONE_PLACE) + r'"[^>]*>(.*?)</a>',
                     lambda m: m.group(1), out, flags=re.S)
    out = out.replace('href="../about/" class="butn-style03 m-1 wow fadeInUp"',
                      'href="../contact-us/" class="butn-style03 m-1 wow fadeInUp"')
    return out


SOCIAL_NETS = ("facebook", "twitter", "linkedin", "instagram", "tiktok", "youtube")


def social_links(out):
    """Two social rows using two icon sets (ti-* in the top bar, fab-* in the footer). Fill
    SOCIAL with your handles and both point at you; leave it empty and the dead links come
    out, instead of sitting there looking like a broken site."""
    def fix(m):
        cls = m.group("cls").lower()
        for net, url in SOCIAL.items():
            if net.replace("x-", "") in cls:
                return m.group(0).replace('href="#"', f'href="{url}" target="_blank" rel="noopener"')
        return ""                                      # no handle for that network
    pat = (r'<li>\s*<a href="#"[^>]*>\s*<i class="(?P<cls>[^"]*(?:'
           + "|".join(SOCIAL_NETS) + r')[^"]*)"[^>]*>[^<]*</i>\s*</a>\s*</li>')
    return re.subn(pat, fix, out, flags=re.S)


def drop_follow_us(out):
    """The demo's social row, minus the links it never had. Give SOCIAL handles and it stays."""
    if SOCIAL:
        return out, 0
    i = out.find("<h4>Follow us</h4>")
    if i < 0:
        return out, 0
    j = out.rfind('<div class="col-sm-6', 0, i)
    k = tag_extent(out, j) if j >= 0 else -1
    return (out[:j] + out[k:], 1) if k > 0 else (out, 0)


def footer_debris(out):
    """What the demo footer carried that we are not going to publish: a newsletter form with
    no list behind it, a fax number, and anchors wrapped around anchors."""
    gone = []
    out, k = drop_widget_containing(out, "Our Newsletter")
    if k:
        gone.append("newsletter heading")
    out, k = drop_widget_containing(out, 'id="wpcf7-f28586-o2"')
    if k:
        gone.append("newsletter form")
    n = len(re.findall(r"<li><span>Fax Id: ?</span>", out))
    out = re.sub(r"<li><span>Fax Id: ?</span>[^<]*</li>", "", out)
    if n:
        gone.append(f"fax number x{n}")
    out, n = re.subn(r'<a href="#"[^>]*>\s*(<a (?:href="mailto:[^"]*"|href="tel:[^"]*")[^>]*>'
                     r'.*?</a>)\s*</a>', lambda m: m.group(1), out)
    if n:
        gone.append(f"{n} nested link(s) flattened")
    return out, gone


def drop_dangling_links(out, folder):
    """The demo body copy links to demo pages we never built - the About block's "Read More"
    pointed at the pricing page, for instance. A short CTA label is better sent to the enquiry
    desk than to a 404; anything longer is reduced to plain text, because a paragraph of text
    is not a button and should not pretend to be one."""
    if not ONLY_BUILT:
        return out, 0, 0
    href = "./" if folder == "contact-us" else "../contact-us/"
    moved = stripped = 0

    def fix(m):
        nonlocal moved, stripped
        whole, target, inner = m.group(0), m.group(1), m.group(2)
        f = _folder_of(target)
        if f is None or f in PAGES or f == "":
            return whole
        text = re.sub("<[^>]+>", "", inner).strip()
        if len(text) <= 14:
            moved += 1
            return whole.replace(target, href)
        stripped += 1
        return inner

    out, _ = re.subn(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', fix, out, flags=re.S)
    return out, moved, stripped


def ensure_brand_assets():
    """Our artwork, generated from the file that was uploaded - rerun whenever the source is
    newer than what it produced, so a better logo drop-in needs no other step."""
    src = os.path.join(ROOT, BRAND_SRC)
    if not os.path.exists(src):
        print(f"  brand: {BRAND_SRC} missing - keeping the demo logo")
        return False
    dest = os.path.join(ROOT, BRAND_DIR)
    need = ["logo.webp", "logo-footer.webp", "favicon-32.png", "favicon-192.png",
            "apple-touch-icon.png", "og-image.jpg", "mark.png"]
    have = [f for f in need if os.path.exists(os.path.join(dest, f))]
    newest = max([os.path.getmtime(os.path.join(dest, f)) for f in have] or [0])
    if len(have) != len(need) or os.path.getmtime(src) > newest:
        import brand_assets
        brand_assets.main()
        print(f"  brand: artwork regenerated from {os.path.basename(BRAND_SRC)}")
    return True


def _hex2rgb(h):
    h = h.lstrip(chr(35))
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def recolour(css):
    """Re-ink the demo palette with the brand's. Elementor writes a colour as a hex, but as
    rgb()/rgba() wherever it carries transparency, so both spellings go; alpha is kept."""
    for old, new in BRAND_MAP.items():
        so = [str(c) for c in _hex2rgb(old)]
        sn = [str(c) for c in _hex2rgb(new)]
        css = re.sub(re.escape(old), new, css, flags=re.I)
        for sep in (", ", ","):
            css = css.replace("rgb(" + sep.join(so) + ")", "rgb(" + sep.join(sn) + ")")
            css = css.replace("rgba(" + sep.join(so), "rgba(" + sep.join(sn))
    return css


def brand_palette(out, outdir):
    """Apply that to the stylesheets without editing the mirror: each sheet carrying a palette
    colour gets a recoloured twin beside it (<name>.brand.css) and only our pages link that."""
    Q = chr(34) + chr(39)
    made, swapped = {}, 0
    for href in sorted(set(re.findall("href=[" + Q + "]([^ " + Q + "]+[.]css)", out))):
        if href.endswith(".brand.css"):
            continue
        src = os.path.normpath(os.path.join(outdir, href.split(chr(63))[0]))
        if not src.startswith(ROOT) or not os.path.exists(src):
            continue
        name = os.path.basename(src)
        if name not in made:
            try:
                txt = open(src, encoding="utf-8", errors="ignore").read()
            except OSError:
                made[name] = None
                continue
            new = recolour(txt)
            if new == txt:
                made[name] = None
                continue
            dst = src[:-4] + ".brand.css"
            with open(dst, "w", encoding="utf-8") as f:
                f.write(new)
            made[name] = os.path.relpath(dst, outdir).replace(os.sep, "/")
        if made[name]:
            out = out.replace(href, made[name])
            swapped += 1
    return out, swapped, sum(1 for v in made.values() if v)


def brand_css(out, outdir):
    """The size of the logo box. Linked last so it outranks the theme rule written for the
    demo artwork, and it touches nothing but the two logo images."""
    rules = []
    for kind, (fn, desk, lap, phone) in BRAND_LOGOS.items():
        sel = ".navbar-brand img" if kind == "header" else ".footer-logo img"
        box = "height:{}px;width:auto;max-height:none"
        rules.append(sel + "{" + box.format(desk) + "}")
        # max-height:none goes in every step, not just the first: the theme's own caps
        # (47px, 42px) would otherwise clamp the height while the width stayed put, and a
        # clamped height with an unclamped width is exactly the squash we are fixing.
        rules.append("@media (max-width:1199.98px){" + sel + "{" + box.format(lap) + "}}")
        rules.append("@media (max-width:767.98px){" + sel + "{" + box.format(phone) + "}}")
    txt = ("/* Generated by build_site.py from BRAND_LOGOS - the size your logo is shown at. "
           "Edit build_site.py, not this file. */" + "".join(rules))
    dst = os.path.join(ROOT, BRAND_DIR, "brand.css")
    prev = open(dst, encoding="utf-8").read() if os.path.exists(dst) else None
    if prev != txt:
        with open(dst, "w", encoding="utf-8") as f:
            f.write(txt)
    href = "../" + BRAND_DIR + "/brand.css"
    if href not in out:
        out = out.replace("</head>", f'<link rel="stylesheet" id="epic-brand-css" href="{href}">'
                                     "</head>", 1)
    return out


def brand_logos(out):
    """The company mark in the header and the footer - white lettering there, since the footer
    is a dark panel - plus tab icons and the mobile home-screen tile."""
    Q = chr(34) + chr(39)
    b = "../" + BRAND_DIR
    swapped = 0
    for kind, (fn, desk, lap, phone) in BRAND_LOGOS.items():
        # the tag carries the file's own pixel size so the browser knows the ratio before the
        # image arrives; brand.css then sets the height and lets the width follow from that
        w = h = 0
        try:
            from PIL import Image
            with Image.open(os.path.join(ROOT, BRAND_DIR, fn)) as im:
                w, h = im.size
        except Exception:
            pass
        size = f' width="{w}" height="{h}"' if w else ""
        alt = f"{BRAND} logo" if kind == "footer" else BRAND
        if kind == "header":
            new = (f'<img id="redux_logo" src="{b}/{fn}" alt="{alt}" title="{BRAND}"'
                   f'{size} decoding="async">')
            out, k = re.subn(r'<img id="redux_logo"[^>]*>', new, out, count=1)
        else:
            new = (f'<img src="{b}/{fn}" alt="{alt}" title="{alt}"{size}'
                   f' loading="lazy" decoding="async">')
            out, k = re.subn("<img[^>]*src=[^>]*footer-light-logo[^>]*>", new, out, count=1)
        swapped += k
    out = re.sub("<link[^>]*rel=[" + Q + "]?(?:shortcut )?icon[^>]*>", "", out)
    out = re.sub("<link[^>]*rel=[" + Q + "]?apple-touch-icon[^>]*>", "", out)
    navy = BRAND_MAP.get("#003751", "#013173")
    out = re.sub('<meta[^>]*msapplication-TileImage[^>]*>',
                 f'<meta name="msapplication-TileImage" content="{b}/favicon-192.png">', out)
    out = out.replace("</head>", f'<meta name="msapplication-TileColor" content="{navy}"></head>', 1)
    icons = (f'<link rel="icon" type="image/png" sizes="32x32" href="{b}/favicon-32.png">'
             f'<link rel="icon" type="image/png" sizes="192x192" href="{b}/favicon-192.png">'
             f'<link rel="apple-touch-icon" href="{b}/apple-touch-icon.png">'
             f'<meta name="theme-color" content="{BRAND_MAP["#003751"]}">')
    if out.count("</head>") != 1:
        raise SystemExit("head is malformed - refusing to write a page with a lost </head>")
    return out.replace("</head>", icons + "</head>", 1), swapped


def brand_social(out, folder, spec):
    """Open-graph tags, so a link pasted into WhatsApp or Facebook shows the logo instead of
    a grey box. The demo head carried none at all."""
    url = SITE + "/" if folder == HOME else f"{SITE}/{folder}/"
    img = f"{SITE}/{BRAND_DIR}/og-image.jpg"
    title = re.sub("<[^>]+>", "", spec["title"])
    tags = (f'<meta property="og:type" content="website">'
            f'<meta property="og:site_name" content="{BRAND}">'
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{spec["desc"]}">'
            f'<meta property="og:url" content="{url}">'
            f'<meta property="og:image" content="{img}">'
            f'<meta name="twitter:card" content="summary_large_image">'
            f'<meta name="twitter:image" content="{img}>')
    return out.replace("</head>", tags + "</head>", 1)
def rebrand(s):
    """Demo brand -> client brand, in visible text and alt/title only. Class names, asset
    paths and the `theme-frexus` slug stay as they are or the theme CSS stops matching."""
    def txt(m):
        return m.group(1) + re.sub(r"\bFrexus\b", BRAND, m.group(2)) + m.group(3)
    s = re.sub(r"(>)([^<>]*)(<)", txt, s)
    def attr(m):
        return f'{m.group(1)}="{re.sub(r"(?i)frexus", BRAND, m.group(2))}"'
    return re.sub(r'\b(alt|title|aria-label)="([^"]*)"', attr, s)
def neutralise_rates(s):
    """The lifted plan cards carry the theme author's prices. Zero them so a demo figure
    can never go out under our name; the layout is untouched."""
    s, n = re.subn(r"(<h5[^>]*>\s*\$\s*)[0-9]+(?:\.[0-9]{1,2})?", lambda m: m.group(1) + "00.00", s)
    return s, n
def restore_icon_fonts():
    """The mirror saved 0-byte stubs in place of the icon fonts, so every FA and Themify
    glyph was an empty box. Fetch the real files once (needs network; a no-op afterwards)
    and return a <style> that re-points the broken @font-face at them."""
    d = os.path.join(ROOT, FA_DIR)
    os.makedirs(d, exist_ok=True)
    def have(f):
        q = os.path.join(d, f)
        return os.path.exists(q) and os.path.getsize(q) > 1024  # fa-v4compatibility is ~4 KB
    todo = [f"{FA_BASE}/{f}" for f in FA_WOFF2 if not have(f)] + \
           [f"{ICON_BASE}/{f}" for f in ICON_FILES if not have(f)]
    got, miss = [], []
    for u in todo:
        f = u.rsplit("/", 1)[-1]
        try:
            with urllib.request.urlopen(u, timeout=90) as r:
                blob = r.read()
            ok = len(blob) > 1024 and (f.endswith(".woff2") and blob[:4] == b"wOF2"
                                       or f.endswith(".woff") and blob[:4] == b"wOFF"
                                       or f.endswith(".ttf") and blob[:4] in (b"\x00\x01\x00\x00", b"true"))
            if ok:
                with open(os.path.join(d, f), "wb") as w:
                    w.write(blob)
                got.append(f"{f} {len(blob) // 1024} KB")
            else:
                miss.append(f)
        except Exception as e:
            miss.append(f"{f} ({type(e).__name__})")
    if got:
        print(f"  icons: restored {', '.join(got)} into {FA_DIR}/")
    if miss:
        print(f"  icons: still missing {', '.join(miss)} — drop them in {FA_DIR}/ by hand")
    if not any(have(f) for f in ICON_FILES):
        return ""
    if fix_themify_css():
        return ""      # theme CSS now points at the restored files, no override needed
    src = ", ".join(f"url('../{FA_DIR}/{f}') format('{fmt}')"
                    for f, fmt in [(x, "woff" if x.endswith(".woff") else "truetype")
                                   for x in ICON_FILES if have(x)])
    # the last @font-face for a family wins, so this beats the theme's dead urls
    return ('<style id="icon-font-fix">'
            '/* build_site.py: the mirror never captured the themify icon font, '
            'this re-points the face at the restored file */'
            "@font-face{font-family:'themify';src:" + src +
            ';font-weight:normal;font-style:normal}</style>')
def fix_themify_css():
    """themify-icons.css still lists the mirror's 0-byte stubs in its @font-face, which
    means five wasted requests per page even after the fonts are back. Rewrite the src
    list in place (idempotent, and every other page in the mirror gets icons too)."""
    path = os.path.join(ROOT, THEMIFY_CSS)
    try:
        c = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return False
    if "themify.clean" in c:
        return True                                   # already re-pointed by an earlier build
    d = os.path.join(ROOT, FA_DIR)
    parts = []
    for f in ICON_FILES:
        q = os.path.join(d, f)
        if os.path.exists(q) and os.path.getsize(q) > 1024:
            fmt = "woff" if f.endswith(".woff") else "truetype"
            parts.append(f'url("../../fonts/{f}") format("{fmt}")')
    if not parts:
        return False
    face = ("@font-face{font-family:'themify';src:" + ", ".join(parts) +
            ";font-weight:normal;font-style:normal}/* themify.clean */")
    c2, n = re.subn(r"@font-face\{[^}]*font-family:'themify';[^}]*\}", lambda m: face, c, count=1)
    if n != 1:
        return False
    try:
        with open(path, "w", encoding="utf-8") as w:
            w.write(c2)
    except OSError:
        return False
    print(f"  icons: re-pointed {THEMIFY_CSS.split('/')[-1]} at the restored font "
          f"({len(c) - len(c2):+d} B)")
    return True
def neutralise_claims(s):
    """Numbers the theme made up about itself: 37k users, 22 awards, and the skill bars'
    percentages. The odometer animates to data-count, so zeroing that is enough to make
    the figure obviously unset without breaking the widget. Send me real numbers and I
    will put them in."""
    s, k1 = re.subn(r'(class="odometer[^"]*")\s*data-count="\d+">[^<]*<',
                     lambda m: m.group(1) + ' data-count="0">0<', s)
    s, k2 = re.subn(r'(<div class="col-6 text-end">)\d{1,3}%(</div>)', r"\g<1>—\g<2>", s)
    return s, k1 + k2
def clean_contact(s):
    for pat, val in DEMO.items():
        s = re.sub(pat, val, s)
    # ... and anything the Cloudflare decode turned up: the demo's own addresses never
    # match our domain, so they are placeholders too and must not go out.
    s = re.sub(r"[A-Za-z0-9._%+-]+@(?:yourdomain\.com|domain\.com|example\.com"
               r"|example\.org|mysite\.com|frexus[a-z]*\.[a-z]+)", EMAIL_PLACE, s)
    # a tel: URI may not contain spaces, however the number is written in the design
    return re.sub(r'href="tel:([^"]*)"',
                  lambda m: 'href="tel:' + re.sub(r"[^0-9+]", "", m.group(1)) + '"', s)
def prune_assets(head, body_markup):
    links = list(re.finditer(r"<link rel='stylesheet' id='([^']+)-css'[^>]*href='([^']*)'[^>]*/?>", head))
    drop = []
    for m in links:
        name, href = m.group(1), m.group(2)
        if name in CSS_DROP_ALWAYS or any(k in name and v not in body_markup for k, v in JS_DROP_IF.items()):
            drop.append(m)
    for m in sorted(drop, key=lambda x: -x.start()):        # back to front: offsets stay valid
        head = head[:m.start()] + head[m.end():]
    js = [m for m in re.finditer(
        r'<script[^>]*src="[^"]*(?:woocommerce|photoswipe|select2|zoom|flexslider|accounting|wp-embed)'
        r'[^"]*"[^>]*></script>', body_markup) if "contact-form-7" not in m.group(0)]
    return head, len(drop), js
def wp_hooks_shim(html):
    dead = re.findall(r'<script[^>]*src="[^"]*wp-includes/js/dist/(?:hooks|i18n)[^"]*"[^>]*></script>', html)
    if not dead:
        return html, 0
    for d in set(dead):
        html = html.replace(d, "")
    shim = ("<script>/* minimal wp.hooks + wp.i18n stand-in: the real files are not in this "
            "export and Elementor only uses them to register filters */\n"
            "(function(){var w=window.wp=window.wp||{};if(!w.hooks){var reg={};"
            "w.hooks={addAction:function(){},addFilter:function(a,f,p,cb){(reg[a]=reg[a]||[]).push(cb);},"
            "removeAction:function(){},removeFilter:function(){},doAction:function(){},removeAllActions:function(){},"
            "applyFilters:function(t,v){(reg[t]||[]).forEach(function(f){try{v=f(v)}catch(e){}});return v;},"
            "doingFilter:function(){return false},hasFilter:function(){return false},runFilters:function(_,t,v){return v}};}"
            "if(!w.i18n){w.i18n={__:function(s){return s},sprintf:function(s){return s},"
            "createI18n:function(){return w.i18n},setLocaleData:function(){},hasTranslation:function(){return false}}}})();</script>\n")
    anchor = re.search(r'<script[^>]*src="[^"]*elementor[^"]*frontend[^"]*\.js[^"]*"[^>]*></script>', html)
    return (html[:anchor.start()] + shim + html[anchor.start():] if anchor
            else html.replace("</body>", shim + "</body>", 1)), len(dead)
def strip_demo_wiring(s):
    gone = []
    for m in reversed(list(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", s))):
        b = m.group(1)
        if re.search(r"wc_add_to_cart_params|woocommerce_params|wc_order_attribution|"
                     r"wc_cart_fragments_params|woocommerce-no-js|var wpcf7 =|_wpemojiSettings|wp-emoji|"
                     r"challenge-platform|email-decode", b):
            g = re.search(r"var (\w+)\s*=", b)
            gone.append(g.group(1) if g else "inline")
            s = s[:m.start()] + s[m.end():]
    for m in reversed(list(re.finditer(r'<script[^>]*src="[^"]*(?:contact-form-7|wp-emoji|cdn-cgi)[^"]*"[^>]*></script>', s))):
        gone.append("external")
        s = s[:m.start()] + s[m.end():]
    s = re.sub(r'(<form\b[^>]*?)action="[^"]*(?:frexuswp|admin-ajax|wp-json)[^"]*"', r'\1action="#"', s)
    s = s.replace("https://frexuswp.websitelayout.net", "").replace(r"https:\/\/frexuswp.websitelayout.net", "")
    return s, gone
def slider_ranges(html):
    out = []
    for m in re.finditer(r'class="[^"]*(?:owl-carousel|swiper-wrapper|slick-slider|slides)[^"]*"', html):
        st = html.rfind("<div", 0, m.start())
        if st < 0:
            continue
        out.append((st, balanced(html, st)))
    return out
def tidy_srcset(tag, base):
    """Keep only the srcset candidates that are really on disk, preferring each one's webp
    twin. A candidate pointing at a 0-byte mirror stub wins over src in every modern
    browser and leaves a hole where the photo should be - so drop it, and drop srcset
    entirely if nothing survives (src alone then governs)."""
    m = re.search(r'srcset="([^"]*)"', tag)
    if not m:
        return tag
    keep = []
    for cand in m.group(1).split(","):
        bits = cand.strip().split(" ", 1)
        if not bits[0]:
            continue
        f = os.path.normpath(os.path.join(base, bits[0].split("?")[0]))
        w = os.path.splitext(f)[0] + ".webp"
        if os.path.exists(w) and os.path.getsize(w) > 1024:
            bits[0] = os.path.relpath(w, base).replace(os.sep, "/")
            f = w
        if not (os.path.exists(f) and os.path.getsize(f) > 1024):
            continue
        keep.append(bits[0] + (" " + bits[1] if len(bits) > 1 else ""))
    if keep:
        return tag[:m.start(1)] + ", ".join(keep) + tag[m.end(1):]
    return tag[:m.start(0) - 1] + tag[m.end(0):]
def optimise_images(html_out, log):
    saved = []
    ranges = slider_ranges(html_out)
    hero_end = html_out.find("</header>")
    def tag(m):
        whole = m.group(0)
        src = re.search(r'src="([^"]+)"', whole)
        if not src:
            return whole
        p = os.path.normpath(os.path.join(os.path.dirname(HTML_OUT[0]), src.group(1)))
        if not os.path.exists(p) or p.endswith(".svg"):
            return whole
        wpth = p[:-4] + ".webp"
        if not os.path.exists(wpth):
            try:
                from PIL import Image
                im = Image.open(p); im.load()
                if max(im.size) > 1500:
                    im.thumbnail((1500, 1500), Image.LANCZOS)
                im.convert("RGBA" if "A" in im.getbands() else "RGB").save(wpth, "WEBP", quality=78, method=6)
            except Exception:
                return whole
        new = os.path.relpath(wpth, os.path.dirname(HTML_OUT[0])).replace(os.sep, "/")
        if os.path.getsize(wpth) >= os.path.getsize(p):
            return whole
        saved.append((os.path.basename(p), os.path.getsize(p) // 1024, os.path.getsize(wpth) // 1024))
        out2 = whole.replace(src.group(0), f'src="{new}"')
        def push(t, *attrs):
            """add attributes to a tag that may be self-closing (<img ... />)"""
            t = t.rstrip()
            t = t[:-2] if t.endswith("/>") else t[:-1]
            return t.rstrip() + " " + " ".join(attrs) + ">"
        out2 = tidy_srcset(out2, os.path.dirname(HTML_OUT[0]))
        if "width=" not in out2:
            try:
                from PIL import Image
                with Image.open(wpth) as im:
                    w, h = im.size
                out2 = push(out2, f'width="{w}"', f'height="{h}"')
            except Exception:
                pass
        in_slider = any(a0 <= m.start() < b0 for a0, b0 in ranges)   # never lazy inside a carousel
        add = []
        if "loading=" not in out2 and "logo" not in new and not in_slider and m.start() > hero_end:
            add.append('loading="lazy"')
        if "decoding=" not in out2:
            add.append('decoding="async"')
        if add:
            out2 = push(out2, *add)
        return out2
    res = re.sub(r"<img\b[^>]*>", tag, html_out)
    if saved and log:
        a = sum(x[1] for x in saved); b = sum(x[2] for x in saved)
        print(f"  images: {len(saved)} → webp, {a} KB → {b} KB")
    return res
SAFETY = ("<noscript><style>.elementor-invisible,.wow{visibility:visible!important;opacity:1!important;animation:none!important}</style></noscript>\n"
          "<script>/* if an animation script fails, nothing stays invisible */\n"
          "addEventListener('load',function(){setTimeout(function(){var d=0;\n"
          "document.querySelectorAll('.elementor-invisible,.wow').forEach(function(e){var cs=getComputedStyle(e);\n"
          "if(cs.visibility==='hidden'||parseFloat(cs.opacity)<.2){e.style.visibility='visible';e.style.opacity=1;d++;}});\n"
          "if(d)console.info('[rescue] revealed '+d+' block(s) left hidden');},1600);});</script>\n")
FORMFIX = ("<script>/* static-site form bridge: no PHP, so a submit becomes a prefilled email.\n"
           "   Swap in Web3Forms/Formspree when you want real sends. */\n"
           "(function(){var TO='" + EMAIL_PLACE + "';\n"
           "document.querySelectorAll('form').forEach(function(f){\n"
           "  f.addEventListener('submit',function(ev){\n"
           "    var act=f.getAttribute('action')||'';\n"
           "  if(act && /^https?:/.test(act) && !/admin-ajax|wp-json|#/.test(act)) return;\n"
           "    ev.preventDefault();var pairs=[];new FormData(f).forEach(function(v,k){if(v&&k[0]!=='_')pairs.push(k+': '+v)});\n"
           "    if(!pairs.length)pairs.push('(empty form)');var msg=pairs.join('\\n');\n"
           "    try{localStorage.setItem('epic-draft',msg)}catch(e){}\n"
           "    window.location.href='mailto:'+TO+'?subject='+encodeURIComponent('Website enquiry')+'&body='+encodeURIComponent(msg);\n"
           "    var n=document.createElement('p');n.style.cssText='margin:.6rem 0 0;font-weight:600;color:#0B6B3A';\n"
           "    n.textContent='Your mail app is opening with these details. If nothing happened, send them to us on WhatsApp.';\n"
           "    f.appendChild(n);});});})();</script>\n")
# ------------------------------------------------------------------ per page
HTML_OUT = [""]           # so optimise_images can resolve relative paths
def build_page(folder, spec, shared):
    outdir = os.path.join(ROOT, folder)
    HTML_OUT[0] = os.path.join(outdir, "index.html")
    print(f"\n=== {folder}/index.html ===")
    chosen, used = [], set()
    for key, phrase, label in spec["sections"]:
        s, pid, depth = read(key)
        used.add(key)
        did, n, frag = pick(containers(s), phrase, label)
        if label == "page banner" and spec.get("banner_text"):
            new = spec["banner_text"]
            frag = re.sub(r"<h1[^>]*>\s*About Us\s*</h1>", f"<h1>{new}</h1>", frag)
            frag = re.sub(r"(<li>)About Us(</li>)", lambda m: m.group(1) + new + m.group(2), frag)
            print(f"  ✓ banner text    {new}")
        chosen.append((pid, rebase(frag, depth), label))
        print(f"  ✓ {label:<16} {key}:{did}  {n:>6,}B")
    h2s = read(HEADER_FROM)[0]
    header = rebase(re.search(r"<header\b[\s\S]*?</header>", h2s).group(0), SOURCES[HEADER_FROM][2])
    header, gone = (rebuild_nav(header, folder) if NAV_ITEMS else trim_menu(header))
    fs, fpid, fdepth = read(FOOTER_FROM)
    footer = rebase(re.search(r"<footer\b[\s\S]*?</footer>", fs).group(0), fdepth)
    if ONLY_BUILT:
        footer, fdrop = drop_unbuilt(footer)
        if fdrop:
            print(f"  footer: {len(fdrop)} link(s) to unbuilt pages removed")
    print(f"  ✓ {'navbar':<16} " + ("flat: " + " · ".join(gone) if NAV_ITEMS
                                       else f"shared, {len(gone)} demo menu items removed"))
    order = []
    for pid, frag, label in chosen:
        if order and order[-1][0] == pid:
            order[-1][1].append(frag)
        else:
            order.append((pid, [frag]))
    main = "\n".join(f'<div data-elementor-type="wp-page" data-elementor-id="{pid}" '
                     f'class="elementor elementor-{pid}">\n' + "\n".join(b) + "\n</div>"
                     for pid, b in order)
    head = re.search(r"<head>[\s\S]*?</head>", h2s, re.I).group(0)
    # One dedupe key per stylesheet: the mirror's hrefs carry ?ver=..., so the query has to
    # come off before two links to the same file are recognised as the same file.
    def csskey(href):
        return os.path.basename(href.split("?")[0])
    linked = {csskey(h) for h in re.findall(r"<link rel='stylesheet'[^>]*href='([^']*)'", head)}
    add, added = [], []

    def link_css(href, css_id, kind):
        """queue one stylesheet, unless it is already linked or is a 0-byte mirror stub"""
        base = os.path.basename(href.split("?")[0])
        query = href[len(href.split("?")[0]):]
        full = f"../wp-content/uploads/elementor/css/{base}{query}"
        if csskey(full) in linked or not css_is_live(full, outdir):
            return False
        linked.add(csskey(full)); added.append(base)
        add.append(f"<link rel='stylesheet' id='{kind}-{css_id}-css' href='{full}' media='all' />")
        return True

    # 1. the Elementor CSS of every demo page we borrowed a section from
    for key in sorted(used):
        if key == HEADER_FROM:
            continue
        for c in elementor_css(read(key)[0]):
            link_css(c, re.search(r"post-(\d+)", c).group(1), "borrowed")

    # 2. ... plus any other page CSS that styles markup which is on this page, wherever it
    # came from. The footer is its own Elementor template (id 14095, 5.7 KB of rules), so a
    # page that borrows nothing else from home-01 would otherwise paint an unstyled footer -
    # exactly what /our-services/ and /contact-us/ were doing before this sweep existed.
    scope_html = header + main + footer
    present = set(re.findall(r'data-id="([0-9a-f]{6,8})"', scope_html))
    for f in sorted(glob.glob(os.path.join(ROOT, "wp-content/uploads/elementor/css/post-*.css"))):
        m = re.search(r"post-(\d+)", os.path.basename(f))
        if not m or f"elementor-{m.group(1)}" not in scope_html:
            continue                                 # this page has no such template
        try:
            body = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if set(re.findall(r"elementor-element-([0-9a-f]{6,8})", body)) & present:
            link_css(f, m.group(1), "needed")
    if add:
        head = head.replace("</head>", "\n".join(add) + "\n</head>")
        print(f"  css: {len(add)} page stylesheet(s) linked for this markup "
              f"({', '.join(added[:4])}{' …' if len(added) > 4 else ''})")
    head = re.sub(r"<title>[\s\S]*?</title>", f"<title>{spec['title']}</title>", head)
    head = re.sub(r"<meta name='description' content='[^']*'>",
                  f"<meta name='description' content='{spec['desc']}'>", head)
    head = re.sub(r"<link rel='canonical'[^>]*>", "", head)
    head = re.sub(r'<link rel="canonical"[^>]*>', "", head)
    head = head.replace("</head>", f'<link rel="canonical" href="{SITE}/{"" if folder==HOME else folder+"/"}">\n</head>')
    head = head.replace("http://fonts.googleapis.com", "https://fonts.googleapis.com")
    head = re.sub(r"<!--\s*Mirrored from[\s\S]*?-->\s*", "", head)
    head = re.sub(r"<!--\s*Added by HTTrack[\s\S]*?-->\s*", "", head)
    body = re.search(r"<body[^>]*>", h2s).group(0)[:-1] + "".join(
        f' elementor-page-{read(k)[1]}' for k in sorted(used) if k != HEADER_FROM) + '">'
    t = h2s.lower().rfind("</footer>")
    tail = rebase(h2s[h2s.lower().find("<script", t): h2s.lower().rfind("</body>")], SOURCES[HEADER_FROM][2])
    out = ("<!doctype html>\n<html class=\"no-js\" lang=\"en-US\">\n" + head + "\n" + body + "\n"
           + header + '\n<main id="main" class="site-main">\n' + main + "\n</main>\n" + footer
           + "\n" + tail + "\n" + SAFETY + FORMFIX + "\n</body>\n</html>\n")
    out = re.sub(r"<!--\s*(Start|End)\s+(header|footer)[\s\S]{0,40}?-->", "", out)
    out = re.sub(r"<link\b[^>]*(?:wp-json|xmlrpc|wlwmanifest|/feed/|api\.w\.org|pingback|shortlink)[^>]*>", "", out)
    out = re.sub(r"""<link rel=["']alternate["'][^>]*>""", "", out)   # oEmbed / RSD autodiscovery
    out = re.sub(r"""<meta name=["']generator["'][^>]*>""", "", out)  # "WordPress 7.1.4", "WooCommerce", "Redux"
    out = re.sub(r'<a[^>]*href="[^"]*/(?:cart|checkout|my-account)/[^"]*"[^>]*>[\s\S]{0,400}?</a>', "", out)
    # navigation between built pages
    for mirror, target in NAV_MAP.items():
        rel = "./" if target == folder else f"../{target}/"
        out = out.replace(f'"{mirror}"', f'"{rel}"').replace(f"'{mirror}'", f"'{rel}'")
    if ONLY_BUILT:                       # nothing may point at a page that will not exist
        def reroute(m):
            pre, href, post = m.group(1), m.group(2), m.group(3)
            parts = [x for x in href.split("?")[0].split("/")
                     if x and x not in (".", "..", "index.html")]
            if not parts or _folder_of(href) in BUILT_FOLDERS:
                return m.group(0)
            # ../service/air-freight/index.html is unbuilt because of "service", not
            # "air-freight", so walk the whole path, deepest folder first
            tgt = next((FALLBACK_LINKS[p] for p in reversed(parts) if p in FALLBACK_LINKS), None)
            if not tgt:
                return m.group(0)
            moved.append(f"{parts[-1]} → {tgt}")
            return f'{pre}{"./" if tgt == folder else "../" + tgt + "/"}{post}'
        moved = []
        out = re.sub(r'''(href=")([^"]*index\.html)(")''', reroute, out)
        if moved:
            print(f"  links: {len(moved)} button/link(s) re-pointed at a page that exists "
                  f"({', '.join(sorted(set(moved)))[:88]})")
    out = out.replace("@HOME@", "./" if folder == HOME else f"../{HOME}/")
    out, ndec = cfemail_decode(out)
    out = cfemail_hash(out)
    out = clean_contact(out)
    # Elementor hands its lightbox the WP title in a JS config blob; that still said
    # "Home 02 – Frexus", which is neither ours nor true of this page.
    out = re.sub(r'("post":\{"id":\d+,"title":")[^"]*(")',
                 lambda m: m.group(1) + urllib.parse.quote(spec["title"][:70]) + m.group(2), out)
    hp = out[:out.find("</head>")]
    new_head, ncss, js_drop = prune_assets(hp, out[out.find("<body"): out.find("<script")])
    if ncss:
        out = new_head + out[out.find("</head>"):]
        print(f"  weight: {ncss} unused stylesheet(s) dropped")
    if js_drop:
        out = re.sub("|".join(re.escape(m.group(0)) for m in js_drop), "", out, count=len(js_drop))
        print(f"  weight: {len(js_drop)} unused script(s) dropped")
    out, nshim = wp_hooks_shim(out)
    if nshim:
        print(f"  deps: {nshim} missing wp-includes/js/dist scripts replaced with a wp.hooks stand-in")
    out, gone2 = strip_demo_wiring(out)
    dead, spans = [], []
    for m in re.finditer(r"<link rel='stylesheet' id='(elementor-gf-local-[^']*)-css'[^>]*href='([^']*)'[^>]*/?>", out):
        href = os.path.normpath(os.path.join(outdir, m.group(2).split("?")[0]))
        try:
            c = open(href, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        urls = re.findall(r"url\(([^)]+)\)", c)
        if urls and all(u.startswith("http://") or not os.path.exists(
                os.path.normpath(os.path.join(os.path.dirname(href), u))) for u in urls):
            dead.append((m.group(1), os.path.getsize(href) // 1024, len(urls)))
            spans.append((m.start(), m.end()))
    for a_, b_ in sorted(spans, reverse=True):
        out = out[:a_] + out[b_:]
    if dead:
        print(f"  fonts: dropped {', '.join(f'{n} ({k} KB→{c} dead files)' for n, k, c in dead)}")
    out = optimise_images(out, log=(folder == HOME))
    iconfix = restore_icon_fonts()
    if iconfix:
        out = out.replace("</head>", iconfix + "\n</head>", 1)
    out = drop_dead_css(out, outdir)
    out = rebrand(out)
    if ensure_brand_assets():
        out, nswap, nmade = brand_palette(out, outdir)
        out, nlogo = brand_logos(out)
        out = brand_css(out, outdir)
        out = brand_social(out, folder, spec)
        if nmade:
            print(f"  brand: {nmade} stylesheet(s) re-inked to your palette")
        if nlogo:
            print(f"  brand: your logo in the header and footer ({nswap} css file(s) recoloured)")
    out, nrate = neutralise_rates(out)
    out, nclaim = neutralise_claims(out)
    if nclaim:
        print(f"  claims: {nclaim} demo figure(s) removed — they were never ours to publish")
    if nrate:
        print(f"  rates: {nrate} demo price(s) zeroed — put your own in")
    if spec.get("todo"):
        phrase, note = spec["todo"]
        out = out.replace(phrase, f"<!-- TODO: {note} -->{phrase}", 1)
    # ---- our words last of all: every stage above keys off the demo's own text, and a
    # replacement that runs before them gets undone (or eats their anchor).
    out, ncards = service_cards(out, folder)
    out, nstat = static_stats(out)
    out, debris = footer_debris(out)
    out = fix_links(out)
    out, nsoc = drop_follow_us(out)
    out, nnet = social_links(out)
    if nnet and not SOCIAL:
        print(f"  copy: {nnet} social icon(s) with no handle behind them removed")
    elif nnet:
        print(f"  copy: {nnet} social link(s) pointed at your handles")
    out = apply_copy(out, COPY_USED)
    out, ndang, nstrip = drop_dangling_links(out, folder)
    if ndang or nstrip:
        print(f"  links: {ndang} dangling link(s) sent to the contact desk, "
              f"{nstrip} reduced to plain text")
    if nsoc:
        print("  copy: footer social row left off (no handles yet - fill SOCIAL to bring it back)")
    if ncards:
        print(f"  copy: {ncards} service card(s) filled with your own service list")
    if nstat:
        print(f"  copy: {nstat} animated counter(s) turned into facts (nothing invented)")
    if debris:
        print("  copy: removed " + ", ".join(debris))
    # ---- guard: refuse to write a page with broken dependencies
    need = {"jquery": "jquery.minf43b", "jquery-migrate": "jquery-migrate.min",
            "bootstrap": "bootstrap.min.js", "theme main.js": "mainf488.js",
            "elementor frontend": "frontend.min"}
    if "owl-carousel" in out:
        need["owl"] = "owl.carousel.js"
    lack = [k for k, v in need.items() if v not in out]
    if lack:
        raise SystemExit(f"  ✗ ABORT {folder}: missing {', '.join(lack)} — a stage ate markup it should not have")
    # Every lifted container and widget carries a data-id. Deleting markup — the failure
    # mode a whole-document rewrite has here — always drops some of them; text rewrites
    # never do. Counted, not just "present", so a section can be damaged and caught even
    # if the same id also appears somewhere else on the page.
    got_ids = collections.Counter(re.findall(r'data-id="([0-9a-f]{6,8})"', out))
    lost = []
    for _pid, frag, lab in chosen:
        want = collections.Counter(re.findall(r'data-id="([0-9a-f]{6,8})"', frag))
        gone = [i for i, c in sorted(want.items()) if got_ids[i] < c]
        if gone:
            lost.append(f"{lab}: {len(gone)}/{len(want)} elements missing "
                        f"(#{', #'.join(gone[:4])})")
    if lost:
        raise SystemExit(f"  ✗ ABORT {folder}: sections damaged — {'; '.join(lost)}")
    if "brand/logo.webp" not in out or "brand/favicon-32.png" not in out:
        raise SystemExit(f"  ✗ ABORT {folder}: the company logo never made it into the page")
    if "brand/brand.css" not in out:
        raise SystemExit(f"  ✗ ABORT {folder}: the logo is unsized (brand.css not linked)")
    dang = sorted({f for f in re.findall(r'''href="[^"]*?([\w-]+)/index\.html"''', out)
                   if f not in PAGES})
    if ONLY_BUILT and dang:
        raise SystemExit(f"  ✗ ABORT {folder}: still links into unbuilt pages: {dang[:4]}")
    dirt = [t for t in FORBIDDEN if t in out]
    for t in dirt[:3]:                                 # where did it come back from?
        i = out.find(t)
        print(f"     ! {t!r} sits in: …{' '.join(out[max(0, i - 70):i + 90].split())}…")
    if dirt:
        raise SystemExit(f"  ✗ ABORT {folder}: demo debris still on the page: {dirt}")
    print(f"  guard: ✓ {len(need)} required scripts · ✓ {len(chosen)} sections · "
          f"✓ {sum(len(re.findall('data-id=', f)) for _, f, _ in chosen)} lifted elements intact · "
          f"✓ img attributes intact · ✓ all image refs on disk")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    bad = [u for u in {m.group(3).split("?")[0].split("#")[0]
                       for m in re.finditer(r'(href|src)\s*=\s*("|\')([^"\']+)\2', out)
                       if not m.group(3).startswith(("http", "mailto", "tel", "data", "javascript", "#"))}
           if not os.path.exists(os.path.normpath(os.path.join(outdir, u))) and u.endswith((".css", ".js"))]
    print(f"  wrote {folder}/index.html  {len(out):,} bytes · broken css/js refs: {len(bad)}")
    for b in bad[:6]:
        print("     ", b[:88])
    return {"folder": folder, "bytes": len(out), "title": re.sub(r"<[^>]+>", "", spec["title"])}
def webpify_backgrounds():
    """The page CSS carries the real weight on this theme: hero and section backgrounds
    are 200-700 KB JPEGs that <img> optimisation never sees. Convert each one referenced
    by a stylesheet we actually link, then rewrite that url() - the originals stay on disk
    and every other page in the mirror keeps working."""
    css = []
    for folder in PAGES:
        p = os.path.join(ROOT, folder, "index.html")
        if not os.path.exists(p):
            continue
        html_txt = open(p, encoding="utf-8").read()
        for u in re.findall(r"""href=['"]([^'"]*post-\d+[^'"]*\.css[^'"]*)['"]""", html_txt):
            f = os.path.normpath(os.path.join(ROOT, folder, u.split("?")[0]))
            if f not in css and f.endswith(".css"):
                css.append(f)
    try:
        from PIL import Image
    except ImportError:
        print("  backgrounds: Pillow not installed - leaving the demo JPEGs as they are")
        return
    before = after = 0
    touched, counted = [], set()
    sz = lambda p: os.path.getsize(p) // 1024
    for f in css:
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        orig = txt
        for u in sorted(set(re.findall(r"""url\(["']?([^"')]+\.(?:jpe?g))["']?\)""", txt))):
            if u.startswith(("http", "data:")):
                continue
            src = os.path.normpath(os.path.join(os.path.dirname(f), u.split("?")[0]))
            if not os.path.exists(src) or os.path.getsize(src) < 20_000:
                continue
            dst = os.path.splitext(src)[0] + ".webp"
            if not os.path.exists(dst):
                try:
                    im = Image.open(src).convert("RGB")
                    im.save(dst, "WEBP", quality=82, method=6)
                except Exception:
                    continue
            if os.path.getsize(dst) >= os.path.getsize(src) * 0.9:
                continue                        # nothing to gain, leave the JPEG alone
            if src not in counted:
                counted.add(src)
                before += os.path.getsize(src)
                after += os.path.getsize(dst)
                touched.append(f"{os.path.basename(src)} {sz(src)}K>{sz(dst)}K")
            txt = re.sub(r'(url\(["\']?)' + re.escape(u) + r'(["\']?\))',
                         lambda m: m.group(1) + u.rsplit(".", 1)[0] + ".webp" + m.group(2), txt)
        if txt != orig:
            with open(f, "w", encoding="utf-8") as w:
                w.write(txt)
    if touched:
        print(f"  backgrounds: {len(touched)} CSS image(s) -> webp, "
              f"{before / 1024:,.0f} KB -> {after / 1024:,.0f} KB  ({', '.join(touched[:4])}"
              f"{' …' if len(touched) > 4 else ''})")
    else:
        print("  backgrounds: already webp")
def main():
    missing = sorted({t for _l, t in NAV_ITEMS if t not in PAGES})
    if missing:
        raise SystemExit("NAV_ITEMS points at page(s) not in PAGES: " + ", ".join(missing))
    built = []
    for folder, spec in PAGES.items():
        built.append(build_page(folder, spec, None))
    unused = [k for k, n in COPY if k not in COPY_USED]
    if unused:
        print(f"  copy: {len(COPY) - len(unused)}/{len(COPY)} pairs fired, "
              f"{len(unused)} matched nothing on any page:")
        for u in unused:
            print("     ! " + " ".join(u.split())[:76])
        raise SystemExit("copy map is out of date with the theme wording - fix the pairs above")
    print(f"  copy: all {len(COPY)} copy pairs applied")
    webpify_backgrounds()
    urls = "\n".join(f'  <url>\n    <loc>{SITE}/{"" if b["folder"]==HOME else b["folder"]+"/"}</loc>'
                     f'\n    <changefreq>monthly</changefreq>\n  </url>' for b in built)
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + urls + "\n</urlset>\n")
    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    print(f"\n{len(built)} pages built: " + ", ".join(f"{b['folder']} ({b['bytes']:,}B)" for b in built))
    print("sitemap.xml + robots.txt written (edit SITE in build_site.py when you pick a domain)")
if __name__ == "__main__":
    main()