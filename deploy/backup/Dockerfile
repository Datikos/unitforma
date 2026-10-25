FROM postgres:18-alpine
RUN apk add --no-cache rclone age bash tar gzip && mkdir -p /backup
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh
ENV BACKUP_CRON="0 2 * * *"
# Run the schedule with busybox crond in the foreground.
CMD ["/bin/sh", "-c", "echo \"$BACKUP_CRON /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1\" > /etc/crontabs/root && exec crond -f -l 8"]
