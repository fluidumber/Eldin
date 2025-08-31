FROM node:20-alpine

WORKDIR /app
COPY package.json /app/
RUN npm install --no-audit --no-fund
COPY . /app
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]