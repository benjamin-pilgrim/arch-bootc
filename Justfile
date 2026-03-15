image_name := env("BUILD_IMAGE_NAME", "arch-bootc")
image_tag := env("BUILD_IMAGE_TAG", "latest")
base_dir := env("BUILD_BASE_DIR", ".")
filesystem := env("BUILD_FILESYSTEM", "ext4")
build_flags := env("BUILD_FLAGS", "--layers=false")
build_tmpdir := env("BUILD_TMPDIR", "/var/tmp/arch-bootc-build")

build-containerfile $image_name=image_name:
    run0 sh -c 'mkdir -p "{{build_tmpdir}}" && TMPDIR="{{build_tmpdir}}" podman build {{build_flags}} -t "${image_name}:latest" .'

build-log $image_name=image_name $image_tag=image_tag:
    run0 sh -c 'mkdir -p "{{build_tmpdir}}" && TMPDIR="{{build_tmpdir}}" podman build {{build_flags}} -t "{{image_name}}:{{image_tag}}" . 2>&1 | tee build.log'

build-log-ts $image_name=image_name $image_tag=image_tag:
    run0 sh -c 'mkdir -p "{{build_tmpdir}}" && TMPDIR="{{build_tmpdir}}" podman build {{build_flags}} -t "{{image_name}}:{{image_tag}}" . 2>&1 | awk '\''{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0; fflush(); }'\'' | tee build.log'

bootc *ARGS:
    run0 podman run \
        --rm --privileged --pid=host \
        -it \
        -v /sys/fs/selinux:/sys/fs/selinux \
        -v /etc/containers:/etc/containers:Z \
        -v /var/lib/containers:/var/lib/containers:Z \
        -v /dev:/dev \
        -e RUST_LOG=debug \
        -v "{{base_dir}}:/data" \
        --security-opt label=type:unconfined_t \
        "{{image_name}}:{{image_tag}}" bootc {{ARGS}}

generate-bootable-image $base_dir=base_dir $filesystem=filesystem:
    #!/usr/bin/env bash
    if [ ! -e "${base_dir}/bootable.img" ] ; then
        fallocate -l 20G "${base_dir}/bootable.img"
    fi
    just bootc install to-disk --composefs-backend --via-loopback /data/bootable.img --filesystem "${filesystem}" --wipe --bootloader systemd

upgrade:
    #!/usr/bin/run0 bash
    set -euxo pipefail
    tmpfile=""
    trap 'rm -f "${tmpfile:-}"' EXIT
    tmpfile="$(mktemp)"
    mkdir -p "{{build_tmpdir}}"
    TMPDIR="{{build_tmpdir}}" podman build {{build_flags}} --iidfile "$tmpfile" -t arch-bootc:latest .
    img_id="$(sed 's/^sha256://' "$tmpfile")"
    echo "Built image: $img_id"
    bootc switch --transport containers-storage "$img_id"
    reboot
