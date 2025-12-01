FROM docker.io/archlinux/archlinux:latest AS base

RUN mv /var/lib/pacman /usr/lib/pacman && echo "DBPath = /usr/lib/pacman/" >> /etc/pacman.conf

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Syu --noconfirm --needed archlinux-keyring

#bootc runtime + build deps
RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    pacman -Sy --noconfirm --needed \
    ostree \
    dracut \
    base-devel rust git

FROM base as bootc-build

RUN git clone --depth 1 "https://github.com/tgnthump/bootc.git" /tmp/bootc

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
    btrfs-progs e2fsprogs xfsprogs dosfstools fuse-overlayfs \
    skopeo \
    dbus \
    dbus-glib \
    glib2 \
    shadow \
    networkmanager \
    network-manager-applet \
    pipewire pipewire-alsa pipewire-pulse pipewire-jack pavucontrol \
    wireplumber \
    openssh \
    man \
    nano \
    vim \
    wget \
    podman \
    just \
    git \
    hyprland \
    hyprpaper \
    hyprpicker \
    hyprlauncher \
    hypridle \
    hyprlock \
    hyprpolkitagent \
    swaync \
    kitty \
    qt5-wayland \
    qt6-wayland \
    waybar \
    otf-font-awesome \
    nautilus \
    uwsm \
    libnewt \
    xdg-desktop-portal-hyprland \
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
    && pacman -Scc --noconfirm

ADD rootfs/ /

RUN --mount=type=cache,target=/var/cache/pacman/pkg \
    --mount=type=cache,target=/usr/lib/pacman/sync \
    mkdir /home/build && \
    chgrp nobody /home/build && \
    chmod g+ws /home/build && \
    setfacl -m u::rwx,g::rwx /home/build && \
    setfacl -d --set u::rwx,g::rwx,o::- /home/build && \
    runuser -u nobody -- bash -c '\
    export GNUPGHOME=/home/build && \
    curl -sS https://downloads.1password.com/linux/keys/1password.asc | gpg --import && \
    cd /home/build && \
    git clone https://aur.archlinux.org/1password.git && \
    cd 1password && \
    makepkg -s \
    ' && \
    pacman -U /home/build/1password/1password-*.tar.zst --noconfirm && \
    rm -rf /home/build

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
