FROM docker.io/mikefarah/yq:4 AS bootc-manifest
COPY packages/bootc.toml /src/bootc.toml
RUN mkdir -p /tmp/out && \
    yq -r '.official.runtime[]' /src/bootc.toml > /tmp/out/packages-official-bootc-runtime.txt && \
    yq -r '.official.build[]' /src/bootc.toml > /tmp/out/packages-official-bootc-build.txt && \
    yq -r '.versions.bootc' /src/bootc.toml > /tmp/out/bootc-version.txt

FROM docker.io/mikefarah/yq:4 AS kernel-manifest
COPY packages/kernel.toml /src/kernel.toml
RUN mkdir -p /tmp/out && \
    yq -r '.official.runtime[]' /src/kernel.toml > /tmp/out/packages-official-kernel-runtime.txt

FROM docker.io/mikefarah/yq:4 AS system-manifest
COPY packages/system.toml /src/system.toml
RUN mkdir -p /tmp/out && \
    yq -r '.official.packages[]' /src/system.toml > /tmp/out/packages-official-system.txt

FROM docker.io/mikefarah/yq:4 AS aur-manifest
COPY packages/aur.toml /src/aur.toml
RUN mkdir -p /tmp/out && \
    yq -r '.aur.packages[]' /src/aur.toml > /tmp/out/packages-aur.txt

FROM docker.io/mikefarah/yq:4 AS keys-manifest
COPY packages/keys.toml /src/keys.toml
RUN mkdir -p /tmp/out && \
    yq -o=json '.keys' /src/keys.toml > /tmp/out/keys.json

FROM docker.io/archlinux/archlinux:latest AS base

RUN mv /var/lib/pacman /usr/lib/pacman && echo "DBPath = /usr/lib/pacman/" >> /etc/pacman.conf

COPY --from=bootc-manifest /tmp/out/packages-official-bootc-runtime.txt /tmp/packages-official-bootc-runtime.txt
COPY --from=bootc-manifest /tmp/out/packages-official-bootc-build.txt /tmp/packages-official-bootc-build.txt
COPY --from=kernel-manifest /tmp/out/packages-official-kernel-runtime.txt /tmp/packages-official-kernel-runtime.txt
COPY --from=system-manifest /tmp/out/packages-official-system.txt /tmp/packages-official-system.txt

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Syu --noconfirm --needed archlinux-keyring

#bootc runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    xargs -a /tmp/packages-official-bootc-runtime.txt -- pacman -Sy --noconfirm --needed

FROM base as bootc-build

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    xargs -a /tmp/packages-official-bootc-build.txt -- pacman -Sy --noconfirm --needed

COPY --from=bootc-manifest /tmp/out/bootc-version.txt /tmp/bootc-version.txt
RUN BOOTC_VERSION="$(cat /tmp/bootc-version.txt)" && \
    git clone --depth 1 --branch "${BOOTC_VERSION}" "https://github.com/bootc-dev/bootc.git" /tmp/bootc

ENV DESTDIR=/sysroot
RUN mkdir -p /sysroot

RUN --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    CARGO_HOME=/root/.cargo \
    CARGO_INCREMENTAL=0 \
    CARGO_BUILD_JOBS=2 \
    CARGO_PROFILE_DEV_OPT_LEVEL=0 \
    CARGO_PROFILE_DEV_DEBUG=0 \
    RUSTFLAGS="-C debuginfo=0" \
    make -C /tmp/bootc bin install-all && \
    rm -rf /tmp/bootc/target

FROM base AS final
COPY --from=bootc-build /sysroot/ /

#dracut runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    xargs -a /tmp/packages-official-kernel-runtime.txt -- pacman -Sy --noconfirm --needed

# Regression with newer dracut broke this
ADD rootfs/usr/lib/dracut /usr/lib/dracut

# Recreate initramfs with dracut to ensure proper integration
RUN KERNEL_VERSION="$(ls -1 /usr/lib/modules | sort -V | tail -n 1)" && \
    dracut --force --no-hostonly --reproducible --zstd --verbose --kver "$KERNEL_VERSION" "/usr/lib/modules/$KERNEL_VERSION/initramfs.img"

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    xargs -a /tmp/packages-official-system.txt -- pacman -Sy --noconfirm --needed && \
    pacman -Scc --noconfirm

ADD rootfs/ /

RUN systemctl --root=/ enable systemd-networkd.service systemd-resolved.service

RUN useradd --uid 1000 --create-home --shell /bin/bash --user-group makepkg && \
    install -d -o makepkg -g makepkg /home/makepkg/.config/pacman && \
    install -d -m 700 -o makepkg -g makepkg /home/makepkg/.gnupg && \
    printf 'MAKEFLAGS="-j%s"\nPKGDEST="/home/makepkg/cache/pkg"\nSRCDEST="/home/makepkg/cache/src"\nBUILDDIR="/home/makepkg/cache/build"\n' "$(nproc)" > /home/makepkg/.config/pacman/makepkg.conf && \
    runuser -u makepkg -- sh -c 'printf "keyserver-options auto-key-retrieve\n" > ~/.gnupg/gpg.conf' && \
    chmod 600 /home/makepkg/.gnupg/gpg.conf

COPY --from=keys-manifest /tmp/out/keys.json /tmp/keys.json
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    runuser -u makepkg -- bash /usr/local/libexec/import-keys.sh /tmp/keys.json

COPY --from=aur-manifest /tmp/out/packages-aur.txt /tmp/packages-aur.txt

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    --mount=type=cache,target=/home/makepkg/cache/aur,uid=1000,gid=1000,mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/src,uid=1000,gid=1000,mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/build,uid=1000,gid=1000,mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/pkg,uid=1000,gid=1000,mode=0775 \
    bash /usr/local/libexec/build-aur.sh /tmp/packages-aur.txt

RUN userdel makepkg

RUN chown root:root /usr/bin/newuidmap /usr/bin/newgidmap && chmod 4755 /usr/bin/newuidmap /usr/bin/newgidmap

# Necessary for general behavior expected by image-based systems
RUN sed -i 's|^HOME=.*|HOME=/var/home|' "/etc/default/useradd" && \
    rm -rf /boot /home /root /usr/local /srv && \
    mkdir -p /var /sysroot /boot /usr/lib/ostree && \
    ln -s var/opt /opt && \
    ln -s var/roothome /root && \
    ln -s var/home /home && \
    ln -s sysroot/ostree /ostree

# Discard trigger files for systemd-firstboot
RUN rm -f /etc/locale.conf /var/log/pacman.log

RUN bootc container lint
RUN date > /build.time
