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

FROM docker.io/archlinux/archlinux:latest AS bootc-base

RUN mv /var/lib/pacman /usr/lib/pacman && echo "DBPath = /usr/lib/pacman/" >> /etc/pacman.conf

COPY --from=bootc-manifest /tmp/out/packages-official-bootc-runtime.txt /tmp/packages-official-bootc-runtime.txt
COPY --from=bootc-manifest /tmp/out/packages-official-bootc-build.txt /tmp/packages-official-bootc-build.txt

RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    pacman -Syu --noconfirm --needed archlinux-keyring

# Build helpers are bind-mounted from run/scripts into /run so they never
# become part of the image layers.
#bootc runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=bind,source=run/scripts/pacman-install.sh,target=/run/pacman-install.sh,ro \
    xargs -a /tmp/packages-official-bootc-runtime.txt -- bash /run/pacman-install.sh

FROM bootc-base as bootc-build

RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=bind,source=run/scripts/pacman-install.sh,target=/run/pacman-install.sh,ro \
    xargs -a /tmp/packages-official-bootc-build.txt -- bash /run/pacman-install.sh

COPY --from=bootc-manifest /tmp/out/bootc-version.txt /tmp/bootc-version.txt
# Keep the bootc checkout and target/ together in one cache mount; Cargo uses
# source paths and mtimes when deciding whether local workspace crates are fresh.
RUN --mount=type=cache,id=arch-bootc-bootc-source,target=/tmp/bootc,sharing=locked \
    BOOTC_VERSION="$(cat /tmp/bootc-version.txt)" && \
    if [ ! -d /tmp/bootc/.git ]; then \
        find /tmp/bootc -mindepth 1 -maxdepth 1 -exec rm -rf {} + && \
        git clone --depth 1 --branch "${BOOTC_VERSION}" "https://github.com/bootc-dev/bootc.git" /tmp/bootc; \
    else \
        git -C /tmp/bootc fetch --depth 1 --force --tags origin "${BOOTC_VERSION}" && \
        git -C /tmp/bootc checkout --force "${BOOTC_VERSION}"; \
    fi && \
    git -C /tmp/bootc clean -fdx -e target

ENV DESTDIR=/sysroot
RUN mkdir -p /sysroot

# Upstream has install targets, but they force xtask manpage generation,
# shell completions, and the integration-test binary. Patch only the target
# dependencies/install docs out so we keep upstream's runtime install recipe.
RUN --mount=type=cache,id=arch-bootc-bootc-source,target=/tmp/bootc,sharing=locked \
    --mount=type=cache,id=arch-bootc-bootc-cargo-registry,target=/root/.cargo/registry,sharing=locked \
    --mount=type=cache,id=arch-bootc-bootc-cargo-git,target=/root/.cargo/git,sharing=locked \
    CARGO_HOME=/root/.cargo \
    CARGO_INCREMENTAL=0 \
    CARGO_BUILD_JOBS=2 \
    CARGO_PROFILE_DEV_OPT_LEVEL=0 \
    CARGO_PROFILE_DEV_DEBUG=0 \
    RUSTFLAGS="-C debuginfo=0" \
    perl -0pi -e 's/bin: manpages/bin:/; s/cargo build --release --features "\$\(CARGO_FEATURES\)" --bins/cargo build --release --features "\$\(CARGO_FEATURES\)" --package bootc --package system-reinstall-bootc --package bootc-initramfs-setup/; s/install: completion/install: bin/; s/\n\tinstall -D -m 0644 -t \$\(DESTDIR\)\$\(prefix\)\/share\/man\/man5 target\/man\/\*\.5; \\\n\tinstall -D -m 0644 -t \$\(DESTDIR\)\$\(prefix\)\/share\/man\/man8 target\/man\/\*\.8; \\//; s/\n\tinstall -D -m 0644 target\/completion\/bootc\.(bash|elvish|fish|powershell|zsh) [^\n]+//g' /tmp/bootc/Makefile && \
    make -C /tmp/bootc install install-ostree-hooks

FROM bootc-base AS final
ARG MAKEPKG_UID=1000
ARG MAKEPKG_GID=1000
COPY --from=bootc-build /sysroot/ /
COPY --from=kernel-manifest /tmp/out/packages-official-kernel-runtime.txt /tmp/packages-official-kernel-runtime.txt
COPY --from=system-manifest /tmp/out/packages-official-system.txt /tmp/packages-official-system.txt

#dracut runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=bind,source=run/scripts/pacman-install.sh,target=/run/pacman-install.sh,ro \
    xargs -a /tmp/packages-official-kernel-runtime.txt -- bash /run/pacman-install.sh

# Regression with newer dracut broke this
ADD rootfs/usr/lib/dracut /usr/lib/dracut

# Recreate initramfs with dracut to ensure proper integration
RUN KERNEL_VERSION="$(ls -1 /usr/lib/modules | sort -V | tail -n 1)" && \
    dracut --force --no-hostonly --reproducible --zstd --verbose --kver "$KERNEL_VERSION" "/usr/lib/modules/$KERNEL_VERSION/initramfs.img"

# Only the package hooks need to exist before system package installation.
# Copy the full rootfs later so UI/config edits do not invalidate package layers.
COPY rootfs/usr/share/libalpm/hooks/90-pam-gnome-keyring.hook /usr/share/libalpm/hooks/90-pam-gnome-keyring.hook
COPY rootfs/usr/share/libalpm/scripts/pam-gnome-keyring-fixup /usr/share/libalpm/scripts/pam-gnome-keyring-fixup

RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=bind,source=run/scripts/pacman-install.sh,target=/run/pacman-install.sh,ro \
    find /var/cache/pacman/pkg -type f -name '*.part' -delete && \
    xargs -a /tmp/packages-official-system.txt -- bash /run/pacman-install.sh --overwrite /usr/share/hypr/hyprland.conf --overwrite /usr/share/hypr/hyprlock.conf --overwrite /usr/share/hypr/hypridle.conf

ADD rootfs/ /

# Apply offline systemd presets so the image ships with expected enabled units.
RUN groupadd --gid "$MAKEPKG_GID" makepkg && \
    useradd --uid "$MAKEPKG_UID" --gid "$MAKEPKG_GID" --create-home --shell /bin/bash makepkg && \
    install -d -o makepkg -g makepkg /home/makepkg/.config/pacman && \
    install -d -m 700 -o makepkg -g makepkg /home/makepkg/.gnupg && \
    printf 'MAKEFLAGS="-j%s"\nPKGDEST="/home/makepkg/cache/pkg"\nSRCDEST="/home/makepkg/cache/src"\nBUILDDIR="/home/makepkg/cache/build"\n' "$(nproc)" > /home/makepkg/.config/pacman/makepkg.conf && \
    runuser -u makepkg -- sh -c 'printf "keyserver-options auto-key-retrieve\n" > ~/.gnupg/gpg.conf' && \
    chmod 600 /home/makepkg/.gnupg/gpg.conf

COPY --from=keys-manifest /tmp/out/keys.json /tmp/keys.json
RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=bind,source=run/scripts/import-keys.sh,target=/run/import-keys.sh,ro \
    runuser -u makepkg -- bash /run/import-keys.sh /tmp/keys.json

COPY --from=aur-manifest /tmp/out/packages-aur.txt /tmp/packages-aur.txt

RUN --mount=type=cache,target=/var/cache/pacman/pkg,sharing=locked \
    --mount=type=cache,target=/usr/lib/pacman/sync,sharing=locked \
    --mount=type=cache,target=/home/makepkg/cache/aur,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/src,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/build,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/pkg,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/xdg,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/go-build,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/go-mod,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/cargo,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=cache,target=/home/makepkg/cache/rustup,uid=${MAKEPKG_UID},gid=${MAKEPKG_GID},mode=0775 \
    --mount=type=bind,source=run/scripts/build-aur.sh,target=/run/build-aur.sh,ro \
    --mount=type=bind,source=run/scripts/build-aur.py,target=/run/build-aur.py,ro \
    bash /run/build-aur.sh /tmp/packages-aur.txt

RUN userdel --force --remove makepkg 2>/dev/null || true && \
    groupdel makepkg 2>/dev/null || true && \
    for db in /etc/passwd /etc/shadow /etc/group /etc/gshadow /etc/subuid /etc/subgid; do \
        [ ! -e "$db" ] || sed -i '/^makepkg:/d' "$db"; \
    done && \
    pwck -r && \
    grpck -r

# Apply offline systemd presets so the image ships with expected enabled units.
RUN systemctl --root=/ preset-all && \
    systemctl --root=/ --global preset-all

RUN chown root:root /usr/bin/newuidmap /usr/bin/newgidmap && chmod 4755 /usr/bin/newuidmap /usr/bin/newgidmap

# Necessary for general behavior expected by image-based systems
RUN sed -i 's|^HOME=.*|HOME=/var/home|' "/etc/default/useradd" && \
    rm -rf /boot /home /root /srv && \
    mkdir -p /var /sysroot /boot /usr/lib/ostree && \
    ln -s var/opt /opt && \
    ln -s var/roothome /root && \
    ln -s var/home /home && \
    ln -s sysroot/ostree /ostree

# Discard trigger files for systemd-firstboot
RUN rm -f /etc/locale.conf /var/log/pacman.log

# Keep /var as a small seed for first boot. bootc copies image /var into
# persistent state during install, and package-manager leftovers here can trip
# composefs/fs-verity validation on Arch before the VM ever boots.
RUN rm -rf \
    /var/cache/* \
    /var/db \
    /var/lib/krb5kdc \
    /var/log/* \
    /var/tmp/* \
    /tmp/*

LABEL containers.bootc=1 \
      ostree.bootable=1

RUN bootc container lint
