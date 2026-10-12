FROM mirror.gcr.io/boky/postfix:v5.1.0-alpine@sha256:6e761312e833947f77af755072c0e77b67d298d127595470a79e9454008dd594
LABEL org.opencontainers.image.source="https://github.com/bingops-com/labops"
# Install the security updates available at build time. CI scans the exact image
# before publishing. /sasl is the unused OAuth Python venv, not Cyrus SASL auth.
# hadolint ignore=DL3017
RUN apk upgrade --no-cache && rm -rf /sasl
# Postfix master drops to its service users; the image also starts OpenDKIM.
# hadolint ignore=DL3002
USER root
