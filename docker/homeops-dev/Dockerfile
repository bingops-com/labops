FROM docker.io/golang:1.26.9-bookworm@sha256:d9c68c2c51161e12fd77e4c6320687c9cd86e1af1e3ad6e6cd63ff970641453c AS go
FROM docker.io/node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node
FROM ghcr.io/coder/coder:v2.36.7@sha256:e8b2743529aea6a1e77bba764c8ec4a04dec65d27ca9caa0ec0b2dbcd3db0565 AS coder_cli
FROM mirror.gcr.io/aquasec/trivy:0.66.0@sha256:086971aaf400beebd94e8300fd8ea623774419597169156cec56eec5b00dfb1e AS trivy_cli
FROM docker.io/postgres:18.4-trixie@sha256:a02db8cac496f15b094798a38254f14d6e00741f709360e5e00bb6668ea31636
LABEL org.opencontainers.image.source="https://github.com/bingops-com/labops"
# hadolint ignore=DL3008
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends awscli bash bash-completion bubblewrap build-essential ca-certificates chromium curl dnsutils docker-cli docker-buildx gh git iproute2 jq less netcat-openbsd openssh-client openssh-server python3 python3-matplotlib python3-numpy python3-pandas python3-pip python3-venv python3-yaml rclone restic ripgrep rsync screen shellcheck tmux unzip vim-tiny && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 1000 --user-group --shell /bin/bash coder && usermod --password '*' coder && mkdir -p /run/sshd /opt/homeops-dev /home/coder/projects && chown 1000:1000 /home/coder/projects && rm -f /etc/ssh/ssh_host_* && ln -s /home/coder/projects /opt/homeops
COPY --from=go /usr/local/go /usr/local/go
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=coder_cli /opt/coder /usr/local/bin/coder
COPY --from=trivy_cli /usr/local/bin/trivy /usr/local/bin/trivy
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY install-tools.py tools.lock.json /opt/homeops-dev/
RUN python3 /opt/homeops-dev/install-tools.py
COPY requirements.txt collections.yml /opt/homeops-dev/
RUN python3 -m venv --system-site-packages /opt/homeops-dev/venv && /opt/homeops-dev/venv/bin/pip install --no-cache-dir --require-hashes -r /opt/homeops-dev/requirements.txt && /opt/homeops-dev/venv/bin/ansible-galaxy collection install -r /opt/homeops-dev/collections.yml -p /opt/homeops-dev/collections
COPY package.json package-lock.json /opt/homeops-dev/npm/
RUN npm ci --prefix /opt/homeops-dev/npm --no-audit --no-fund && ln -s /opt/homeops-dev/npm/node_modules/.bin/codex /usr/local/bin/codex
COPY homeops-dev-check.sh /usr/local/bin/homeops-dev-check
RUN chmod 0755 /usr/local/bin/homeops-dev-check && for tool in ansible ansible-playbook ansible-galaxy ansible-lint yamllint pytest; do ln -s "/opt/homeops-dev/venv/bin/$tool" "/usr/local/bin/$tool"; done
ENV PATH="/home/coder/.local/bin:/usr/local/go/bin:${PATH}" LANG=C.UTF-8 CHROMIUM=/usr/bin/chromium ANSIBLE_COLLECTIONS_PATH=/home/coder/.ansible/collections:/opt/homeops-dev/collections CLUSTERCTL_DISABLE_VERSIONCHECK=true DISABLE_AUTOUPDATER=1
USER 1000:1000
# runc creates the cwd before mounted home contents are present; avoid a symlink.
WORKDIR /home/coder
EXPOSE 2222
ENTRYPOINT []
CMD ["/bin/bash"]
