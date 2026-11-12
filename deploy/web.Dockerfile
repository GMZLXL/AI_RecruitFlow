FROM node:24-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
COPY frontend/package.json ./frontend/package.json
RUN npm ci --ignore-scripts
COPY frontend ./frontend
RUN npm run build --workspace frontend

FROM nginx:stable-alpine
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /build/frontend/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
