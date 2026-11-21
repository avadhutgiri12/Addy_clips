FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S addy && adduser -S addy -G addy
COPY --from=build --chown=addy:addy /app/.next/standalone ./
COPY --from=build --chown=addy:addy /app/.next/static ./.next/static
USER addy
EXPOSE 3000
CMD ["node", "server.js"]

