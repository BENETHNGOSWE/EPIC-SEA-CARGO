#!/usr/bin/env bash
# install-site.sh - serve the site with the VPS's own nginx. No Docker, no image, no build.
#
#   curl -sO https://raw.githubusercontent.com/BENETHNGOSWE/EPIC-SEA-CARGO/main/install-site.sh
#   bash install-site.sh --dry-run          # read-only: shows every step
#   bash install-site.sh                    # does it, asks before touching ports/other apps
#
# Safe to re-run: it pulls instead of cloning, and only rewrites its own server block.
# Options: --domain other.com   --dir /var/www/other   --branch deploy   --force (no prompts)
set -euo pipefail

DOMAIN="epicseacargo.com"
DIR="/var/www/epic"
BRANCH="deploy"
REPO="https://github.com/BENETHNGOSWE/EPIC-SEA-CARGO.git"
DRY=false FORCE=false
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=true ;;
        --force)   FORCE=true ;;
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
command -v nginx >/dev/null 2>&1 || { echo "  nginx is not installed"; $DRY || run apt-get install -y -qq nginx; }
NGXV=$(command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 | cut -d/ -f2 || echo "not installed yet")
echo "  git $(git --version | awk '{print $3}') · nginx ${NGXV}"

say "2/6  who owns ports 80 and 443"
OWNERS="$($SUDO ss -ltnp 2>/dev/null | grep -E ':(80|443)[[:space:]]' || true)"
if [ -n "$OWNERS" ]; then
    echo "$OWNERS" | sed 's/^/  /'
    if echo "$OWNERS" | grep -qiE 'docker-proxy|traefik|envoy'; then
        echo "  >> a container proxy (Coolify/Traefik) is holding those ports."
        echo "  >> nginx cannot bind 80 while that is true. Either free them in Coolify"
        echo "  >> (Server -> Proxy) or keep Coolify and use the bind-mount option in"
        echo "  >> VPS-NATIVE.md instead of this script."
        $FORCE || { printf '  continue anyway? [y/N] '; read -r a; [ "$a" = y ] || exit 1; }
    fi
else
    echo "  free"
fi

say "3/6  the files"
if [ -d "$DIR/.git" ]; then
    run git -C "$DIR" fetch --depth 1 origin "$BRANCH"
    run git -C "$DIR" reset --hard "origin/$BRANCH"
else
    run $SUDO mkdir -p "$(dirname "$DIR")"
    run $SUDO git clone --depth 1 -b "$BRANCH" "$REPO" "$DIR"
fi
for f in index.html 404.html about/index.html our-services/index.html contact-us/index.html; do
    $DRY || [ -s "$DIR/$f" ] || { echo "  !! $DIR/$f is missing or empty - aborting"; exit 1; }
done
printf '  site: %s files, %s\n' "$($DRY && echo '?' || find "$DIR" -type f -not -path '*/.git/*' | wc -l)" "$($DRY && echo '?' || du -sh "$DIR" | cut -f1)"

say "4/6  nginx server block -> $CONF"
if $DRY; then
    echo "  would write: root $DIR, gzip, 1-year immutable cache on assets, /about -> /about/,"
    echo "  no-cache html + nosniff/X-Frame-Options/Referrer-Policy, error_page 404 -> /404.html,"
    echo "  404 for .git/, Dockerfile, nginx.conf, docker-compose.yml"
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

    location ~ /\.git  { return 404; }
    location ~ ^/(Dockerfile|nginx\.conf|docker-compose\.ya?ml|VPS-NATIVE\.md|install-site\.sh)$ { return 404; }

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
echo "  Updating the site later is one command:  git -C ${DIR} fetch --depth 1 origin ${BRANCH} && git -C ${DIR} reset --hard origin/${BRANCH}"
