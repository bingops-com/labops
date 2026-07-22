FROM registry.k8s.io/kubectl:v1.36.1 AS kubectl
FROM ghcr.io/jqlang/jq:1.8.1 AS jq

FROM ghcr.io/actions/actions-runner:2.334.0

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# renovate: datasource=github-releases depName=cli/cli versioning=semver
ARG GH_VERSION=2.93.0
ARG TARGETARCH
RUN curl --fail --show-error --silent --location "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${TARGETARCH}.tar.gz" | tar --extract --gzip --strip-components=2 --directory=/usr/local/bin "gh_${GH_VERSION}_linux_${TARGETARCH}/bin/gh"
COPY --from=kubectl /bin/kubectl /usr/local/bin/kubectl
COPY --from=jq /jq /usr/local/bin/jq
USER runner
