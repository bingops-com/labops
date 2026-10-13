FROM docker.io/golang:1.26.9-bookworm@sha256:d9c68c2c51161e12fd77e4c6320687c9cd86e1af1e3ad6e6cd63ff970641453c AS go
FROM docker.io/node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node
FROM docker.io/ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
LABEL org.opencontainers.image.source="https://github.com/bingops-com/labops"
# hadolint ignore=DL3008
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bash build-essential ca-certificates curl git jq less openssh-client openssh-server pipx python3 python3-matplotlib python3-numpy python3-pandas python3-pip python3-venv ripgrep tmux unzip vim-tiny && rm -rf /var/lib/apt/lists/* && userdel -r ubuntu && useradd --create-home --uid 1000 --user-group --shell /bin/bash coder && usermod --password '*' coder && mkdir -p /run/sshd && rm -f /etc/ssh/ssh_host_* && chmod 0755 /run/sshd
COPY --from=go /usr/local/go /usr/local/go
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV PATH="/home/coder/.local/bin:/usr/local/go/bin:${PATH}" LANG=C.UTF-8
USER 1000:1000
WORKDIR /home/coder
EXPOSE 2222
CMD ["/bin/bash"]
