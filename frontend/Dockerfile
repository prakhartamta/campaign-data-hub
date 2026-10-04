# The frontend, built once and served by nginx.
# Two stages: node compiles the React code into static files, then only those files are copied
# into an nginx image, so node, node_modules and the source never ship.
FROM node:22-alpine AS build

WORKDIR /app

# The lockfile before the source, for the same reason as requirements.txt in the backend image:
# editing a component reuses the installed-packages layer instead of reinstalling everything.
# npm ci rather than npm install: it installs exactly what the lockfile says, or fails.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Runs tsc before vite, so a type error fails the image build instead of shipping.
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
# No CMD: the nginx image's own starts nginx in the foreground, which is what keeps the container up.
