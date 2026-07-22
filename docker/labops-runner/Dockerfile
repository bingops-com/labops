FROM registry.k8s.io/kubectl:v1.36.1 AS kubectl
FROM ghcr.io/cli/cli:2.93.0 AS github-cli
FROM ghcr.io/jqlang/jq:1.8.1 AS jq

FROM ghcr.io/actions/actions-runner:2.334.0

USER root
COPY --from=kubectl /bin/kubectl /usr/local/bin/kubectl
COPY --from=github-cli /usr/bin/gh /usr/local/bin/gh
COPY --from=jq /jq /usr/local/bin/jq
USER runner
