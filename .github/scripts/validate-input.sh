#!/usr/bin/bash
case "${IMAGE_NAME}" in
  coder-bootstrap|coder-workspace|homeops-dev)
    echo "Retired Coder images cannot be built or published." >&2
    exit 1
    ;;
esac

missing_input=false

if [ -z "${IMAGE_NAME}" ]; then
  echo "❌ Missing image name"
  missing_input=true
fi

if [ ! -f "${DOCKERFILE_PATH}" ]; then
  echo "❌ Dockerfile not found at path: ${DOCKERFILE_PATH}"
  missing_input=true
fi

if [ ! -d "${BUILD_CONTEXT}" ]; then
  echo "❌ Build context not found at path: ${BUILD_CONTEXT}"
  missing_input=true
fi

if [ "$missing_input" = true ]; then
  exit 1
fi
