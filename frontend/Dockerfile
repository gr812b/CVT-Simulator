# Build context: frontend/
# CI uses: context: ./frontend, file: ./frontend/Dockerfile

FROM node:20-alpine AS build

WORKDIR /app

# Vite embeds VITE_* values at build time. Leave this blank for the default
# production deployment: the browser calls same-origin /api/v1/* and nginx
# proxies those requests to the backend container.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package*.json ./
RUN npm ci

COPY . ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
