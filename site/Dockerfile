FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY index.html /usr/share/nginx/html/index.html
RUN sed -i 's/listen       8080;/listen 8080;/' /etc/nginx/conf.d/default.conf
EXPOSE 8080
