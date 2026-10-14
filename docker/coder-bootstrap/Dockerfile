FROM ghcr.io/coder/coder:v2.36.7@sha256:e8b2743529aea6a1e77bba764c8ec4a04dec65d27ca9caa0ec0b2dbcd3db0565 AS cli
FROM docker.io/python:3.13.7-alpine3.22@sha256:9ba6d8cbebf0fb6546ae71f2a1c14f6ffd2fdab83af7fa5669734ef30ad48844
LABEL org.opencontainers.image.source="https://github.com/bingops-com/labops"
COPY --from=cli /opt/coder /usr/local/bin/coder
RUN addgroup -g 1000 coder && adduser -D -u 1000 -G coder coder
USER 1000:1000
WORKDIR /tmp
RUN coder server create-admin-user --help >/dev/null
ENTRYPOINT ["python3", "-u", "/scripts/bootstrap.py"]
