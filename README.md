# Opinionated Arch Bootc Image

## Development Tasks

This repo uses `mise` for tool and task management.

```bash
mise trust
mise install
mise tasks ls
```

Canonical local workflows:

```bash
# Build the local image with layer cache enabled
mise run image:build

# Force a cold rebuild without layer cache
mise run image:build-clean

# Refresh bootable.img only when the built image ID changed
mise run image:artifact

# Run the full local pipeline
mise run test:all

# Boot the graphical VM smoke directly against the current artifact
mise run test:vm:graphical

# Build first, refresh the artifact if needed, then boot the graphical VM and leave it open
mise run run:vm:graphical
```

Additional test entry points:

```bash
# Container smoke tests against a chosen image tag
BUILD_IMAGE_NAME=arch-bootc mise run test:container

# VM smoke tests against an already booted guest over SSH
BOOTC_VM_SSH='root@127.0.0.1 -p 2222' mise run test:vm

# Sandbox VM smoke against an existing stamped artifact
mise run test:vm:sandbox

# Sandbox graphical VM smoke against an existing stamped artifact
mise run test:vm:sandbox-graphical
```

Useful overrides:

```bash
# Optional: if SSH user is non-root, prefix privileged commands
BOOTC_VM_ROOT_PREFIX='sudo -n' BOOTC_VM_SSH='user@vm' mise run test:vm

# Optional: choose a different forwarded SSH port or user
BOOTC_VM_SSH_PORT=2223 BOOTC_VM_SSH_USER=root mise run run:vm:graphical

# Optional: disable systemd-ssh-generator path and provide your own SSH setup
BOOTC_VM_USE_SYSTEMD_SSH_GENERATOR=0 mise run run:vm:graphical

# Optional: customize the generated SSH listener for systemd-ssh-generator
BOOTC_VM_SYSTEMD_SSH_LISTEN='0.0.0.0:22' mise run run:vm:graphical

# Optional: tune VM boot log verbosity (default: quiet)
BOOTC_VM_LOG_LEVEL=quiet mise run run:vm:graphical
BOOTC_VM_LOG_LEVEL=normal mise run run:vm:graphical
BOOTC_VM_LOG_LEVEL=debug mise run run:vm:graphical

# Optional: disable injected serial kernel logs or fully customize injected kernel cmdline
BOOTC_VM_SERIAL_KERNEL_LOG=0 mise run run:vm:graphical
BOOTC_VM_KERNEL_CMDLINE='console=ttyS0 loglevel=7' mise run run:vm:graphical
```

Host-mutating workflow:

```bash
# Build the image and switch the local host via bootc
mise run host:upgrade
```

Builds use `podman build --network=host` by default to avoid rootless DNS resolution failures during `pacman` steps. Override `BUILD_FLAGS` if you need different networking.

## Composefs Kernel Choice

This image still uses the bootc composefs backend, but it is pinned to
`linux-lts` rather than Arch's current mainline kernel.

The reason is upstream issue
[`bootc-dev/bootc#2174`](https://github.com/bootc-dev/bootc/issues/2174): Linux
7.0.x regressed overlayfs/fs-verity behavior in a way that breaks native bootc
composefs boot on Arch. The failure shows up during early boot with errors like:

```text
overlayfs: lower file '...' has no fs-verity digest
Failed to execute /sbin/init, giving up: Input/output error
```

This repo chooses the simpler recovery path: keep the native bootc initramfs
flow and use a kernel line that does not hit the regression. Once the kernel
side fix is available in Arch, the image can move back to the regular
`linux` package.

## Package Manifests

Package inputs are split by concern under `packages/`:

- `packages/bootc.toml`
- `packages/kernel.toml`
- `packages/system.toml`
- `packages/aur.toml`
- `packages/keys.toml`

This keeps build cache boundaries sane:

- changing `packages/system.toml` or `packages/aur.toml` does not invalidate the expensive `bootc` build layer
- changing `packages/keys.toml` only affects key import
- only `packages/bootc.toml` affects the `bootc-build` stage
