# Deploying the site without a build step

The site is 102 files: HTML, CSS, images, a favicon. Nothing to compile, nothing to install,
no PHP, no database. Whatever runs it only has to read files and answer HTTP.

Branch to serve: **`deploy`** (the site). Branch `main` is the source: the theme mirror, the
builder, and its root `index.html` is the vendor's demo page. If a deploy log says `:main`,
stop - the branch is wrong and nothing else matters until it is fixed.

---

## Option A - nginx from apt, Coolify not involved at all (zero containers)

This is "the normal way". Cost: nginx (~2 MB RAM) + certbot. It only works if **Coolify's
proxy is not holding ports 80/443** - check first:

```bash
sudo ss -ltnp | grep -E ':(80|443)\s'
```

`nginx` or nothing → go ahead. `docker-proxy` / `traefik` → Coolify owns those ports and you
need Option B, or you free the ports in Coolify (Server → Proxy) for the whole box.

```bash
# 1. the files
sudo apt-get update && sudo apt-get install -y git nginx
sudo git clone --depth 1 -b deploy https://github.com/BENETHNGOSWE/EPIC-SEA-CARGO.git /var/www/epic

# 2. the server block (root + cache + gzip + /about -> /about/ + 404 page + the repo files hidden)
sudo tee /etc/nginx/sites-available/epicseacargo.com >/dev/null <<'CONF'
server {
    listen 80;
    listen [::]:80;
    server_name epicseacargo.com www.epicseacargo.com;
    root /var/www/epic;
    index index.html;

    # the served folder is a git checkout: build files and history are not part of the site
    location ~ /\.git  { return 404; }
    location ~ ^/(Dockerfile|nginx\.conf|docker-compose\.ya?ml|VPS-NATIVE\.md)$ { return 404; }

    gzip on;
    gzip_types text/css application/javascript image/svg+xml text/plain application/xml;
    gzip_min_length 1024;

    location ~* \.(css|js|svg|png|jpg|jpeg|webp|woff2|woff|ttf|ico)$ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }
    location ~* \.html$ {
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }
    rewrite ^/([a-z0-9-]+[^./]*)$ /$1/ permanent;
    location / { try_files $uri $uri/ =404; }
    error_page 404 /404.html;
}
CONF
sudo ln -sf /etc/nginx/sites-available/epicseacargo.com /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 3. TLS - only after DNS already points here (A @ and A www -> this VPS)
sudo certbot --nginx -d epicseacargo.com -d www.epicseacargo.com --redirect
sudo certbot renew --dry-run
```

Updating the site, from now on, forever:

```bash
sudo git -C /var/www/epic pull --ff-only
```

---

## Option B - keep Coolify (you get its UI, backups and TLS) but with no build

Coolify starts containers, that is all it knows. What you can remove is the *build*: point it
at a stock nginx image and hand it the folder. **New Resource → Docker Run** (not "Deploy from
Git", not Nixpacks, not Dockerfile):

| field | value |
|---|---|
| Name | `epic-site` |
| Docker Image | `nginx:1.27-alpine` |
| Command / Build settings / Env | empty - do not touch |
| Ports Exposed | `80` |
| Volumes | `/var/www/epic:/usr/share/nginx/html:ro` and `/var/www/epic/nginx.conf:/etc/nginx/conf.d/default.conf:ro` |
| Domains | `epicseacargo.com`, `www.epicseacargo.com` → port 80, Let's Encrypt on, Force HTTPS on |

Steps: run the two `git` lines from Option A first (Coolify only mounts the folder, it does
not create it), then create the resource above. Update = the same `git pull`. No redeploy, no
image build, no Dockerfile, no `mkdir` bug, ~4 MB of RAM while running.

**This is the branch Coolify users should take** (Build Pack dropdown: choose **Docker
Compose**, not Nixpacks / Static / Dockerfile - the first two run a build, the last one is the
`Dockerfile location` field that fails on a folder like this). New Resource → Deploy from Git →
repository `BENETHNGOSWE/EPIC-SEA-CARGO` → **branch `deploy`** → Build Pack **Docker Compose** →
Compose location `docker-compose.yml`. That file carries the two mounts above, joins the
`coolify` network and ships its own Traefik labels for `epicseacargo.com` + `www` with
`certresolver=letsencrypt`, so **leave Coolify's Domains field empty** - filling it in creates a
second router for the same host. No `ports:` key either, on purpose: publishing 80 would collide
with Coolify's proxy. Requires Server → Proxy → Let's Encrypt to have an email set, or the
certificate request stalls. Again: no build step, nothing to compile, and `git pull` is the only
update.

---

## About "Docker uses huge resources for a static site"

Correct about the build, not about the container. Building an image for this site = ~30 s of
CPU, 100-200 MB of layer churn and a cache to keep - and that is exactly the step Option A and
Option B both delete. Running nginx, in a container or from apt, is the same 2-5 MB of RAM and
the same file reads. So: the thing you objected to is gone in both options, and Option B keeps
Coolify's TLS and panel for free.

If the VPS is doing nothing else but this site and the second company's, the honest cheapest
setup is Option A on the box you already pay for, and leaving Coolify for the apps that need a
build (mail helpers, admin tools, the second site if it is WordPress).
