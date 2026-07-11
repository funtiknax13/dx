# Prod build image — used on the server to produce static assets for nginx.
# Not used during local dev (frontend runs via Dockerfile.dev there instead).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM scratch AS export
COPY --from=build /app/dist /dist
