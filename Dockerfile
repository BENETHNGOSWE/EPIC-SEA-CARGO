# The static site. Build context = the dist/ folder (Coolify: Build Pack = Dockerfile,
# Build context path = dist). No build step, no PHP, no WordPress.
FROM nginx:1.27-alpine
COPY . /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
