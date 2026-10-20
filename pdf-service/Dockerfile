# Playwright's image already has Chromium and its system libraries; the version must match package.json.
FROM mcr.microsoft.com/playwright:v1.47.2-jammy
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./
ENV NODE_ENV=production
EXPOSE 3100
CMD ["node", "server.js"]
