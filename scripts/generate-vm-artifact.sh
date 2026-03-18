#!/usr/bin/env bash

set -eu
base_dir="${BUILD_BASE_DIR:-.}"
bootable="${BOOTABLE_IMAGE_PATH:-$base_dir/bootable.img}"
bootable_image_id_file="${BOOTABLE_IMAGE_ID_FILE:-$bootable.image-id}"
image_name="${BUILD_IMAGE_NAME:-arch-bootc}"
image_tag="${BUILD_IMAGE_TAG:-local}"

if [ "${image_name#*/}" = "$image_name" ]; then
  image_ref="localhost/$image_name:$image_tag"
else
  image_ref="$image_name:$image_tag"
fi

if ! podman image exists "$image_ref"; then
  echo "Image $image_ref not found; building it now..."
  BUILD_IMAGE_NAME="$image_name" BUILD_IMAGE_TAG="$image_tag" mise run build-log
fi

image_id="$(
  podman image inspect --format json "$image_ref" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); obj=data[0] if isinstance(data,list) else data; print(obj.get("Id",""))'
)"
if [ -z "$image_id" ]; then
  echo "Failed to determine image ID for $image_ref"
  exit 1
fi
BUILD_IMAGE_NAME="$image_name" BUILD_IMAGE_TAG="$image_tag" BUILD_BASE_DIR="$base_dir" BOOTABLE_IMAGE_PATH="$bootable" mise run generate-bootable-image
printf '%s\n' "$image_id" >"$bootable_image_id_file"

echo "VM artifact ready:"
echo "  image: $image_ref"
echo "  image id: $image_id"
echo "  disk: $bootable"
echo "  stamp: $bootable_image_id_file"
