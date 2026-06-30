#!/bin/sh
# updateapp_for_old.sh — build, tag, and push the image to Docker Hub
# (uses legacy "docker-compose" v1 binary)
# Usage: ./updateapp_for_old.sh

set -e

version=$(head version -n1)

IMAGE="prateekrajgautam/telegramdatamanager:latest"
IMAGE_VER="prateekrajgautam/telegramdatamanager:$version"

echo "⏹  Stopping running container (if any)..."
docker-compose down || true

echo "⬇️  Pulling base image updates..."
docker-compose pull || true

echo "🔨 Building image: $IMAGE"
docker-compose -f docker-compose-build.yml build --no-cache ## optional
docker-compose -f docker-compose-build.yml build

echo "⬆️  Pushing to Docker Hub: $IMAGE"
docker push "$IMAGE"

# get image id, tag it with version and push
IMAGE_ID=$(docker images --format '{{.ID}}' "$IMAGE")
docker tag "$IMAGE" "$IMAGE_VER"
docker push "$IMAGE_VER"

echo "✅ Done — $IMAGE is live on Docker Hub."

# -----------------------------------------------------------
# Start and test locally after pushing
# -----------------------------------------------------------
echo "🚀 Starting locally..."
docker-compose up -d
echo "📋 Logs (Ctrl+C to detach)..."
docker-compose logs -f
