FROM mongo:8.0-noble
COPY --chmod=755 entrypoint.sh /opt/hwsuk/entrypoint.sh
COPY bootstrap.js health.js /opt/hwsuk/
ENV MONGO_INITDB_ROOT_USERNAME=hwsuk_admin \
    MONGO_INITDB_ROOT_PASSWORD_FILE=/data/configdb/admin-password \
    HOME=/tmp
USER mongodb
ENTRYPOINT ["/opt/hwsuk/entrypoint.sh"]
CMD ["mongod", "--replSet", "rs01", "--keyFile", "/data/configdb/replica-key", "--bind_ip_all"]
