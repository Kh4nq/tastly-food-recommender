FROM node:22-alpine
WORKDIR /app

# Install deps first so this layer is cached until package files change
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
