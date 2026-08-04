# The stock mongo:7.0 image does not bundle mongosh (split into a separate
# package). This Dockerfile builds a minimal image with mongosh installed
# so init-cluster.sh has a shell to run its rs.initiate()/sh.addShard()
# commands with.
FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg ca-certificates && \
    curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" \
      > /etc/apt/sources.list.d/mongodb-org-7.0.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends mongodb-mongosh && \
    apt-get purge -y curl gnupg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /scripts
COPY init-cluster.sh .
RUN chmod +x init-cluster.sh

ENTRYPOINT ["bash", "/scripts/init-cluster.sh"]
