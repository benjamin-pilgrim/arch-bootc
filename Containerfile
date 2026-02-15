FROM docker.io/archlinux/archlinux:latest AS base

RUN mv /var/lib/pacman /usr/lib/pacman && echo "DBPath = /usr/lib/pacman/" >> /etc/pacman.conf

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Syu --noconfirm --needed archlinux-keyring

#bootc runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Sy --noconfirm --needed \
    ostree \
    dracut \
    base-devel git

FROM base as bootc-build

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Sy --noconfirm --needed rust go-md2man

RUN git clone --depth 1 --branch v1.12.1 "https://github.com/bootc-dev/bootc.git" /tmp/bootc

ENV DESTDIR=/sysroot
RUN mkdir -p /sysroot

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    make -C /tmp/bootc bin install-all

FROM base AS final
COPY --from=bootc-build /sysroot/ /

#dracut runtime deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Sy --noconfirm --needed \
    linux \
    linux-firmware \
    intel-ucode

# Regression with newer dracut broke this
ADD rootfs/usr/lib/dracut /usr/lib/dracut

# Recreate initramfs with dracut to ensure proper integration
RUN KERNEL_VERSION="$(ls -1 /usr/lib/modules | sort -V | tail -n 1)" && \
    dracut --force --no-hostonly --reproducible --zstd --verbose --kver "$KERNEL_VERSION" "/usr/lib/modules/$KERNEL_VERSION/initramfs.img"

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Sy --noconfirm --needed \
    btrfs-progs e2fsprogs xfsprogs dosfstools fuse-overlayfs fuse2 \
    skopeo \
    dbus \
    dbus-glib \
    glib2 \
    shadow \
    networkmanager \
    network-manager-applet \
    openbsd-netcat \
    pipewire pipewire-alsa pipewire-pulse pipewire-jack pavucontrol \
    wireplumber \
    openssh \
    man \
    nano \
    vim \
    unzip \
    go-yq \
    wget \
    podman \
    just \
    git \
    hyprland \
    hyprpaper \
    hyprpicker \
    hypridle \
    hyprlock \
    hyprpolkitagent \
    swaync \
    grim \
    slurp \
    kitty \
    qt5-wayland \
    qt6-wayland \
    waybar \
    otf-font-awesome \
    nautilus \
    gnome-keyring \
    seahorse \
    uwsm \
    libnewt \
    xdg-desktop-portal-hyprland \
    xdg-desktop-portal-gtk \
    brightnessctl \
    playerctl \
    usbutils \
    fprintd \
    firefox \
    mesa \
    intel-media-driver \
    intel-media-sdk \
    vulkan-intel \
    intel-gpu-tools \
    libva-utils \
    vdpauinfo \
    vulkan-tools \
    chrony \
    throttled \
    fwupd \
    tlp \
    flatpak \
    flatpak-builder \
    bluez \
    bluez-utils \
    blueman \
    ttf-jetbrains-mono-nerd \
    code \
    jq \
    mise \
    rustup \
    go \
    gobject-introspection \
    github-cli \
    libqalculate \
    fd \
    imagemagick \
    wl-clipboard \
    libnotify \
    ffmpeg4.4 \
    chromium \
    && pacman -Scc --noconfirm

ADD rootfs/ /

RUN useradd --create-home --shell /bin/bash --user-group makepkg && \
    install -d -o makepkg -g makepkg /home/makepkg/.config/pacman && \
    install -d -m 700 -o makepkg -g makepkg /home/makepkg/.gnupg && \
    install -d -o makepkg -g makepkg /home/makepkg/out && \
    printf 'MAKEFLAGS="-j%s"\nPKGDEST="/home/makepkg/out"\n' "$(nproc)" > /home/makepkg/.config/pacman/makepkg.conf && \
    runuser -u makepkg -- sh -c 'printf "keyserver-options auto-key-retrieve\n" > ~/.gnupg/gpg.conf' && \
    chmod 600 /home/makepkg/.gnupg/gpg.conf

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    runuser -u makepkg -- bash -c '\
    set -euo pipefail && \
    umask 022 && \
    export GNUPGHOME="$HOME/.gnupg" && \
    install -d -m 700 "$GNUPGHOME" && \
    curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import \
    '

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    runuser -u makepkg -- bash -c '\
    set -euo pipefail && \
    umask 022 && \
    build_aur_pkg() { \
        local pkg="$1" && \
        ( \
            set -euo pipefail && \
            local workdir="$(mktemp -d)" && \
            trap "rm -rf \"$workdir\"" EXIT && \
            cd "$workdir" && \
            git clone --depth 1 --single-branch "https://aur.archlinux.org/${pkg}.git" && \
            cd "$pkg" && \
            makepkg -s \
        ); \
    } && \
    for pkg in \
        1password \
        1password-cli \
        jetbrains-toolbox \
        cloudflare-warp-bin \
        walker \
        hyprshot-git \
        elephant \
        elephant-desktopapplications \
        elephant-calc \
        elephant-runner \
        elephant-files \
        elephant-websearch \
        elephant-clipboard \
	parsec-bin; do \
        build_aur_pkg "$pkg"; \
    done \
    ' && \
    find /home/makepkg/out -maxdepth 1 -type f -name "*-debug-*.pkg.tar.zst" -delete && \
    pacman -U /home/makepkg/out/*.pkg.tar.zst --noconfirm && \
    rm -f /home/makepkg/out/*.pkg.tar.zst

RUN chown root:root /usr/bin/newuidmap /usr/bin/newgidmap && chmod 4755 /usr/bin/newuidmap /usr/bin/newgidmap

# Necessary for general behavior expected by image-based systems
RUN sed -i 's|^HOME=.*|HOME=/var/home|' "/etc/default/useradd" && \
    rm -rf /boot /home /root /usr/local /srv && \
    mkdir -p /var /sysroot /boot /usr/lib/ostree && \
    ln -s var/opt /opt && \
    ln -s var/roothome /root && \
    ln -s var/home /home && \
    ln -s sysroot/ostree /ostree && \
    echo "$(for dir in opt usrlocal home srv mnt ; do echo "d /var/$dir 0755 root root -" ; done)" | tee -a /usr/lib/tmpfiles.d/bootc-base-dirs.conf && \
    echo "d /var/roothome 0700 root root -" | tee -a /usr/lib/tmpfiles.d/bootc-base-dirs.conf && \
    echo "d /run/media 0755 root root -" | tee -a /usr/lib/tmpfiles.d/bootc-base-dirs.conf && \
    printf "[composefs]\nenabled = yes\n[sysroot]\nreadonly = true\n" | tee "/usr/lib/ostree/prepare-root.conf"

# Discard trigger files for systemd-firstboot
RUN rm /etc/locale.conf /var/log/pacman.log

RUN bootc container lint
RUN date > /build.time
