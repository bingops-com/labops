FROM docker.io/node:22.20.0-alpine3.22 AS web
LABEL name="portal"

WORKDIR /src
# hadolint ignore=DL3018
RUN apk add --no-cache git \
    && git clone --depth 1 --branch master \
      https://github.com/bingops-com/portal.git . \
    && npm --prefix web ci --no-audit --no-fund \
    && npm --prefix web run build

FROM docker.io/golang:1.25-alpine3.22 AS build
ENV CGO_ENABLED=0
WORKDIR /src
COPY --from=web /src/go.mod /src/go.sum ./
RUN go mod download
COPY --from=web /src/cmd ./cmd
COPY --from=web /src/internal ./internal
COPY --from=web /src/web/embed.go ./web/embed.go
COPY --from=web /src/web/dist ./web/dist
RUN go build -trimpath -ldflags="-s -w" -o /out/portal ./cmd/portal

FROM gcr.io/distroless/static-debian12:nonroot
LABEL org.opencontainers.image.source="https://github.com/bingops-com/portal"
ENV PORTAL_ADDR=:3000
ENV PORTAL_CONFIG=/etc/portal/portal.yaml
ENV PORTAL_DATA=/data
COPY --from=build /out/portal /portal
USER 65532:65532
EXPOSE 3000
ENTRYPOINT ["/portal"]
