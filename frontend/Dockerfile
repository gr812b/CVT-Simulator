# Build context: repository root.
# CINDER/backend contracts are generated in an isolated build stage, then the
# TypeScript client is generated before the Vite build. Generated contracts do
# not need to be committed to the repository.

FROM python:3.10-slim AS contracts

WORKDIR /repo/backend
COPY backend/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install -r requirements.txt
COPY backend/ ./
RUN /opt/venv/bin/python -m app.scripts.export_contract_artifacts --output-dir /contracts

FROM node:20-alpine AS build

WORKDIR /app

# Vite embeds VITE_* values at build time. Leave this blank for the default
# production deployment: the browser calls same-origin /api/v1/* and nginx
# proxies those requests to the backend container.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV CINDER_BACKEND_ARTIFACTS=/contracts

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
COPY --from=contracts /contracts /contracts
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
