FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY svsgold-frontend/package.json ./
RUN npm install
RUN npm install xlsx

# Copy source code
COPY svsgold-frontend/ .

# Build React (Vite)
RUN npm run build


# ----------- PRODUCTION STAGE -----------
FROM nginx:alpine

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built app to /crm path
RUN mkdir -p /usr/share/nginx/html/crm
COPY --from=builder /app/dist /usr/share/nginx/html/crm

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]