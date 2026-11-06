# Epic Sea Cargo — website

Two branches, and they are not the same thing:

| branch | what it is | who uses it |
|---|---|---|
| **`deploy`** (default) | **the website**: 99 plain files — HTML, CSS, images, favicon, `robots.txt`, `sitemap.xml`. This is what visitors get. No WordPress, no PHP, no container files. | your server pulls this |
| `main` | the workshop: the page builder, the static exporter, the checker, the brand assets, and the demo pages sections were lifted from. Its root `index.html`/`404.html` are a copy of the built site, so even a wrong-branch checkout shows your homepage instead of the theme demo | only for changing the site |

So if you open the repository and see `index.html`, `about/`, `our-services/`, `contact-us/`,
`wp-content/` and nothing else — that is correct. The build scripts and the deploy script are on
`main`: switch the branch dropdown, or go to
`https://github.com/BENETHNGOSWE/EPIC-SEA-CARGO/tree/main`.

## On the VPS — first time

```bash
sudo apt-get install -y git nginx
curl -sO https://raw.githubusercontent.com/BENETHNGOSWE/EPIC-SEA-CARGO/main/install-site.sh
sudo bash install-site.sh          # clone the site, write the nginx block, nginx -t, reload, self-test
```

Then TLS, once it prints that the pages answer:

```bash
sudo certbot --nginx -d epicseacargo.com -d www.epicseacargo.com --redirect
```

## After any change

```bash
sudo git -C /var/www/epic pull
```

No rebuild, no redeploy, no restart: nginx reads the files on each request.

## Checking it

```bash
for p in "" about/ our-services/ contact-us/; do
  printf "%-16s %s\n" "/$p" "$(curl -s -o /dev/null -w '%{http_code}' https://epicseacargo.com/$p)"
done
curl -s https://epicseacargo.com/ | grep -o '<title>[^<]*'      # want: Epic Sea Cargo — Ocean Freight…
```

Four `200`s and your own title is a healthy site. If the title says **Frexus**, the folder being
served is a `main` checkout — re-clone as above.

## Still placeholders, on purpose

Phone number and social links (they print but do not dial until supplied), and your own
photographs — every card is still the demo's image. No invented founding years, statistics,
client counts or rates anywhere.
