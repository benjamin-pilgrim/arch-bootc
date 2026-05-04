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

## Composefs Verity Workaround

This image intentionally uses the bootc composefs backend, but currently carries
an Arch-specific initramfs workaround for Linux 7.0.x kernels.

The upstream issue is tracked as
[`bootc-dev/bootc#2174`](https://github.com/bootc-dev/bootc/issues/2174).
Linux commit `f77f281b61183a5c0b87e6a4d101c70bd32c1c79` changed fs-verity
state handling in a way that breaks composefs through overlayfs
`verity=require`. The failure shows up during boot as messages like:

```text
overlayfs: lower file '...' has no fs-verity digest
Failed to execute /sbin/init, giving up: Input/output error
```

This is a kernel/overlayfs/fs-verity regression, not a corrupt bootc image. The
same composefs repository can be mounted directly with `mount.composefs`, while
bootc's native initramfs setup path fails when overlayfs asks for strict verity
validation.

Until the kernel-side fix is available in Arch, the image overrides
`bootc-root-setup.service` in the initramfs to run
`/usr/lib/bootc/arch-composefs-setup`. That script still mounts the bootc
composefs deployment selected by the `composefs=` kernel argument, but it does
so via:

```text
mount -t composefs -o basedir=/sysroot/composefs/objects \
  /sysroot/composefs/images/<deployment> /run/bootc-composefs-root
```

It then preserves the normal bootc state shape by mounting:

- `/etc` from `/sysroot/state/deploy/<deployment>/etc`
- `/var` from `/sysroot/state/os/default/var`
- the physical root at `/sysroot`, remounted read-only

This keeps bootc composefs bootable and leaves deployment selection driven by
bootc's `composefs=` boot entry. The tradeoff is that this bypasses the broken
strict overlayfs fs-verity enforcement path, so it should not be treated as the
final sealed-root integrity model.

Remove this workaround once a kernel with the overlayfs/fs-verity fix is in use
and the native `/usr/lib/bootc/initramfs-setup setup-root` path boots cleanly
again.

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
