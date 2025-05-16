#!/usr/bin/bash
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
