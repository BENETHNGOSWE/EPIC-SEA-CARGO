# epicseacargo.com - how it is served

Plain nginx from apt, reading plain files. No Docker, no container, no image, no build step,
no Coolify, no PHP, no WordPress.

## Deploy / update (one command, on the VPS)

```bash
curl -sO https://raw.githubusercontent.com/BENETHNGOSWE/EPIC-SEA-CARGO/main/install-site.sh
sudo bash install-site.sh --dry-run     # read-only preview of all six steps
sudo bash install-site.sh               # does it
```

The script: installs `git` + `nginx` if missing → reports what owns ports 80/443 → puts the
site at `/var/www/epic` (clone the first time, `fetch + reset --hard` afterwards) → checks the
four pages and `404.html` are present and non-empty → writes
`/etc/nginx/sites-available/epicseacargo.com` → `nginx -t` **before** reloading → self-tests
`/`, a hidden file and a missing page → prints the certbot command.

`sudo bash install-site.sh --files-only` is the content-update path: refresh the files, run the
checks, touch nothing else.

## What the server block gives you

gzip; `Cache-Control: public, max-age=31536000, immutable` on css/js/images/fonts;
`no-cache` on `.html` so an update is visible immediately; `X-Content-Type-Options`,
`X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`; `/about` -> `/about/` so relative asset paths
survive; `error_page 404 /404.html`; and 404 for `.git/` and any build file, because the web root
is a git checkout.

TLS: `sudo certbot --nginx -d epicseacargo.com -d www.epicseacargo.com --redirect` and it
renews itself via the certbot timer. Needs DNS settled first: `A @ -> VPS IP` and `A www -> VPS
IP` (the domain currently resolves to 5.189.178.106), and ports 80/443 free.

## If the script says a container proxy owns :80

That is Coolify's Traefik. Delete the Coolify application for this site (`docker ps` first, to
see what else you would take down) - or if other apps must stay, tell me and I'll wire the site to
a port Traefik forwards to. Nothing about the site itself changes either way: it is the same
folder of files.

## Rebuilding the site from source (this repo, branch `main`)

```bash
python3 build_site.py      # splices the Frexus sections + your brand + copy -> the 4 pages
python3 export_site.py     # -> dist/ : every href/src/srcset/url() re-based, self-checked
python3 check_pages.py     # audit over a local preview server (serve.py, port 8090)
```

`export_site.py` also copies the verified `index.html`, `404.html`, `robots.txt` and `sitemap.xml` to this branch's root (`mirror_root`) - the mirror's own home page lives in `home-01/`, which is what `build_site.py` reads - so serving `main` by mistake can no longer publish the vendor's demo page.

Then push `dist/` to branch **`deploy`** and the VPS pulls it. `deploy` contains the site and
nothing else - 99 files, no container config, no theme source, no PHP.

## Placeholders still waiting on you

`PHONE` in `build_site.py` (5 places print a number but do not dial until it is set), `SOCIAL`
(empty means the social rows are removed, so nothing dead ships), your own photographs (every card
is still a demo image), and confirmation of `SITE = https://epicseacargo.com`.
