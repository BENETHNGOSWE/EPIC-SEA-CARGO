# The static site. No build step, no PHP, no WordPress.
# Coolify: branch `deploy` · Build Pack = Dockerfile · Build context path = `.`
FROM nginx:1.27-alpine

# Without this line nginx runs on its stock defaults: no gzip (2 MB instead of ~600 KB per
# first load), no cache headers, no /about -> /about/, and its own 404 page instead of ours.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY . /usr/share/nginx/html

# Build inputs, not web content - they must not be downloadable from the site.
RUN rm -f /usr/share/nginx/html/Dockerfile /usr/share/nginx/html/nginx.conf \
          /usr/share/nginx/html/.dockerignore

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
