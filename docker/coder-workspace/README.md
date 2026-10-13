# Coder workspace image

The existing image workflow builds `ghcr.io/bingops-com/coder-workspace` from this directory. `VERSION` provides a release tag; the workspace template must be pinned to the published digest before its production import. No new registry credential is required: publication uses the repository's scoped Actions token.

Ubuntu, Node and Go base images are pinned by digest. Python, build tools, OpenSSH, Git, tmux and scientific plotting packages are installed at image build time. Replacing a workspace pod does not run an installation script or require an apt mirror. Rebuilding the image can pick up Ubuntu package updates; its new digest must be reviewed before adoption.

The development user is `coder`, UID/GID 1000, with no sudo and no password login. The workspace has no Docker socket, host filesystem, privileged capability or Kubernetes account token. OpenSSH runs as this user on port 2222, with a persistent host key and the Git-managed authorized public key.

The image is reconstructible from this Dockerfile and the pinned bases. Its publication workflow and GHCR package visibility are external operational prerequisites. Make the package public for anonymous cluster pulls, or configure a namespace-local pull credential before use. Recovery and operator ownership are documented in [the Coder runbook](../../apps/workloads/coder/README.md).
