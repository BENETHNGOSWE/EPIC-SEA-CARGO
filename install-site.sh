#!/usr/bin/env bash
# install-site.sh - the whole deployment. Plain nginx from apt, this repo's files on disk.
# Nothing else is required: no Docker, no container, no image, no build step, no Coolify.
#
#   curl -sO https://raw.githubusercontent.com/BENETHNGOSWE/EPIC-SEA-CARGO/main/install-site.sh
#   bash install-site.sh --dry-run          # read-only: shows every step
#   bash install-site.sh                    # does it, asks before touching ports/other apps
#   bash install-site.sh --files-only       # only the site folder + checks (for Coolify users:
#                                           # this is the prerequisite the compose expects)
#
# Safe to re-run: it pulls instead of cloning, and only rewrites its own server block.
# Options: --domain other.com   --dir /var/www/other   --branch deploy   --force (no prompts)
set -euo pipefail

DOMAIN="epicseacargo.com"
DIR="/var/www/epic"
BRANCH="deploy"
REPO="https://github.com/BENETHNGOSWE/EPIC-SEA-CARGO.git"
DRY=false FORCE=false FILES_ONLY=false
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=true ;;
        --force)   FORCE=true ;;
        --files-only) FILES_ONLY=true ;;
        --domain)  DOMAIN="$2"; shift ;;
        --dir)     DIR="$2"; shift ;;
        --branch)  BRANCH="$2"; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac; shift
done
CONF="/etc/nginx/sites-available/${DOMAIN}"
MARKER="# epic-site managed block - safe to edit, this script only replaces this file"
say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
run()  { if $DRY; then printf '  would run: %s\n' "$*"; else echo "  + $*"; "$@"; fi; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

say "1/6  checking the box"
for c in git curl; do
    command -v "$c" >/dev/null 2>&1 || { echo "  missing: $c"; $DRY || { $FORCE && SUDO="sudo"; run apt-get update -qq; run apt-get install -y -qq git curl nginx; }; }
done
if ! $FILES_ONLY; then
    command -v nginx >/dev/null 2>&1 || { echo "  nginx is not installed"; $DRY || run apt-get install -y -qq nginx; }
fi
NGXV=$(command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 | cut -d/ -f2 || echo "not installed yet")
echo "  git $(git --version | awk '{print $3}') · nginx ${NGXV}"

say "2/6  who owns ports 80 and 443"
OWNERS="$($SUDO ss -ltnp 2>/dev/null | grep -E ':(80|443)[[:space:]]' || true)"
if [ -n "$OWNERS" ]; then
    echo "$OWNERS" | sed 's/^/  /'
    if echo "$OWNERS" | grep -qiE 'docker-proxy|traefik|envoy|apache'; then
        echo "  >> something else is already answering on 80/443, so nginx cannot bind them."
        echo "  >> That process must go (or move to another port) before this site can own the"
        echo "  >> domain. Name of the owner is in the lines above; nothing was changed."
        $FORCE || { printf '  continue anyway? [y/N] '; read -r a; [ "$a" = y ] || exit 1; }
    fi
else
    echo "  free"
fi

fetch_files() {
    if [ -d "$DIR/.git" ]; then
        run $SUDO git -C "$DIR" fetch --depth 1 origin "$BRANCH"
        run $SUDO git -C "$DIR" checkout -q -B "$BRANCH" FETCH_HEAD
        run $SUDO git -C "$DIR" reset --hard FETCH_HEAD
        return
    fi
    # A bind mount whose host path is missing makes Docker create it - as empty directories,
    # including a DIRECTORY named nginx.conf, which then cannot be mounted onto a file. That
    # stub is the only thing this removes, and only when it is provably empty.
    if [ -e "$DIR" ] && [ -z "$(find "$DIR" -mindepth 1 ! -path "$DIR/nginx.conf" ! -path "$DIR/nginx.conf/*" 2>/dev/null)" ]; then
        if [ -d "$DIR/nginx.conf" ] && [ -z "$(ls -A "$DIR/nginx.conf")" ]; then
            echo "  removing the empty stub Docker created at $DIR"
            run $SUDO rm -rf "$DIR"
        fi
    elif [ -e "$DIR" ]; then
        echo "  !! $DIR exists, is not a git checkout, and holds files this script did not create:"
        find "$DIR" -maxdepth 2 | sed "s|^|     |" | head -20
        echo "  Move it away or pass --dir /var/www/other. Nothing was deleted."
        exit 1
    fi
    run $SUDO mkdir -p "$(dirname "$DIR")"
    run $SUDO git clone --depth 1 -b "$BRANCH" "$REPO" "$DIR"
}

say "3/6  the files"
fetch_files
for f in index.html 404.html about/index.html our-services/index.html contact-us/index.html; do
    $DRY || [ -s "$DIR/$f" ] || { echo "  !! $DIR/$f is missing or empty - aborting"; exit 1; }
done
if ! $DRY; then
    [ -d "$DIR" ] || { echo "  !! $DIR is not a directory"; exit 1; }
    [ -s "$DIR/wp-content/uploads/brand/logo.webp" ] || echo "  note: no logo.webp yet (brand assets not rebuilt?)"
    TITLE=$(sed -n 's@.*<title>\([^<]*\)</title>.*@\1@p' "$DIR/index.html" | head -1)
    case "$TITLE" in
      "Epic Sea Cargo"*) echo "  page title ok: ${TITLE:0:58}" ;;
      *) echo "  !! $DIR/index.html is: ${TITLE:0:64}"
         echo "  !! That is not your site - it is the theme demo (branch main is the mirror)."
         echo "  !! Serve branch $BRANCH instead: sudo git -C $DIR fetch --depth 1 origin $BRANCH \\"
         echo "       && sudo git -C $DIR checkout -B $BRANCH FETCH_HEAD && sudo git -C $DIR reset --hard FETCH_HEAD"
         exit 1 ;;
    esac
    echo "  webroot ok: $(find "$DIR" -maxdepth 1 -type d | wc -l) dirs · $(du -sh "$DIR" | cut -f1)"
fi
printf '  site: %s files, %s\n' "$($DRY && echo '?' || find "$DIR" -type f -not -path '*/.git/*' | wc -l)" "$($DRY && echo '?' || du -sh "$DIR" | cut -f1)"

if $FILES_ONLY; then
    say "done - files only. Nothing else to configure:"
    echo "  Files are in place. Re-run the script (without --files-only) to write the nginx block,"
    echo "  or use this for content changes only:  sudo bash $0 --files-only"
    exit 0
fi

say "4/6  nginx server block -> $CONF"
if $DRY; then
    echo "  would write: root $DIR, gzip, 1-year immutable cache on assets, /about -> /about/,"
    echo "  no-cache html + nosniff/X-Frame-Options/Referrer-Policy, error_page 404 -> /404.html,"
    echo "  404 for dotfiles (.git) and for the script itself"
else
    if [ -f "$CONF" ] && ! grep -q "epic-site managed block" "$CONF"; then
        echo "  !! $CONF already exists and is not ours; leaving it alone"; exit 1
    fi
    $SUDO tee "$CONF" >/dev/null <<CONF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};
    ${MARKER}
    root ${DIR};
    index index.html;

    location ~ /\. { return 404; }          # .git and anything else hidden in the web root
    location = /install-site.sh { return 404; }

    gzip on;
    gzip_types text/css application/javascript image/svg+xml text/plain application/xml;
    gzip_min_length 1024;

    location ~* \.(css|js|svg|png|jpg|jpeg|webp|woff2|woff|ttf|ico)$ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files \$uri =404;
    }
    location ~* \.html\$ {
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }
    rewrite ^/([a-z0-9-]+[^./]*)\$ /\$1/ permanent;
    location / { try_files \$uri \$uri/ =404; }
    error_page 404 /404.html;
}
CONF
    $SUDO ln -sfn "$CONF" "/etc/nginx/sites-enabled/${DOMAIN}"
    if [ -e /etc/nginx/conf.d/default.conf ] && grep -q "listen.*80" /etc/nginx/conf.d/default.conf 2>/dev/null; then
        echo "  note: a default server is still listening on 80 in conf.d - disabling it"
        $SUDO rm -f /etc/nginx/conf.d/default.conf
    fi
    if [ -L /etc/nginx/sites-enabled/default ]; then $SUDO rm -f /etc/nginx/sites-enabled/default; fi
fi

say "5/6  validate and reload"
run $SUDO nginx -t
run $SUDO systemctl reload nginx
if ! $DRY; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1/ || echo 000)
    leak=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1/nginx.conf || echo 000)
    n404=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1/no-such-page || echo 000)
    SERVED=$(curl -s -m 5 -H "Host: ${DOMAIN}" http://127.0.0.1/ | sed -n 's@.*<title>\([^<]*\)</title>.*@\1@p' | head -1)
    case "$SERVED" in
      "Epic Sea Cargo"*) echo "  visitors get: ${SERVED:0:58}" ;;
      *) echo "  !! nginx is serving: ${SERVED:-nothing} - NOT your page. Check root= in $CONF" ; exit 1 ;;
    esac
    printf '  localhost says: / -> %s (want 200) · /nginx.conf -> %s (want 404) · /no-such-page -> %s (want 404)\n' "$code" "$leak" "$n404"
    [ "$code" = 200 ] || echo "  !! not serving yet - if 000, nginx is not bound to :80 (see step 2)"
fi

say "6/6  TLS - only once DNS points here"
getent hosts "$DOMAIN" | awk '{print "  '"$DOMAIN"' -> "$1}' || echo "  $DOMAIN does not resolve yet"
if ! $DRY; then
    command -v certbot >/dev/null 2>&1 || { echo "  installing certbot"; run $SUDO apt-get install -y -qq certbot python3-certbot-nginx; }
    echo "  run:  sudo certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} --redirect"
    echo "  then: curl -sI https://${DOMAIN}/ | grep -iE 'HTTP|cache-control'"
fi
echo
echo "  Updating the site later is one command (the folder is root-owned, so use sudo):"
echo "    sudo git -C ${DIR} fetch --depth 1 origin ${BRANCH} && sudo git -C ${DIR} reset --hard origin/${BRANCH}"
