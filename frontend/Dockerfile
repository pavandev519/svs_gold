# Frontend React + Vite Dockerfile
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY svsgold-frontend/package.json ./

# Install dependencies
RUN npm install
RUN npm install xlsx

# Copy source code
COPY svsgold-frontend/ .

# Build the React application
RUN npm run build

# Install nginx
RUN apk add --no-cache nginx

# Create custom nginx configuration
RUN mkdir -p /etc/nginx/http.d
COPY nginx.conf /etc/nginx/http.d/default.conf

# Copy built files to nginx html directory
RUN mkdir -p /usr/share/nginx/html && cp -r dist/* /usr/share/nginx/html/

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
