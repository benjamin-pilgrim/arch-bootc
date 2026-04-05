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
BUILD_IMAGE_TAG=local mise run image:build

# Force a cold rebuild without layer cache
BUILD_IMAGE_TAG=local mise run image:build-clean

# Refresh bootable.img only when the built image ID changed
BUILD_IMAGE_TAG=local mise run image:artifact

# Run the full local pipeline
BUILD_IMAGE_TAG=local mise run test:all

# Boot the graphical VM smoke directly against the current artifact
BUILD_IMAGE_TAG=local mise run test:vm:graphical

# Build first, refresh the artifact if needed, then boot the graphical VM and leave it open
BUILD_IMAGE_TAG=local mise run run:vm:graphical
```

Additional test entry points:

```bash
# Container smoke tests against a chosen image tag
BUILD_IMAGE_NAME=arch-bootc BUILD_IMAGE_TAG=local mise run test:container

# VM smoke tests against an already booted guest over SSH
BOOTC_VM_SSH='root@127.0.0.1 -p 2222' mise run test:vm

# Sandbox VM smoke against an existing stamped artifact
BUILD_IMAGE_TAG=local mise run test:vm:sandbox

# Sandbox graphical VM smoke against an existing stamped artifact
BUILD_IMAGE_TAG=local mise run test:vm:sandbox-graphical
```

Useful overrides:

```bash
# Optional: if SSH user is non-root, prefix privileged commands
BOOTC_VM_ROOT_PREFIX='sudo -n' BOOTC_VM_SSH='user@vm' mise run test:vm

# Optional: choose a different forwarded SSH port or user
BOOTC_VM_SSH_PORT=2223 BOOTC_VM_SSH_USER=root BUILD_IMAGE_TAG=local mise run run:vm:graphical

# Optional: disable systemd-ssh-generator path and provide your own SSH setup
BOOTC_VM_USE_SYSTEMD_SSH_GENERATOR=0 BUILD_IMAGE_TAG=local mise run run:vm:graphical

# Optional: customize the generated SSH listener for systemd-ssh-generator
BOOTC_VM_SYSTEMD_SSH_LISTEN='0.0.0.0:22' BUILD_IMAGE_TAG=local mise run run:vm:graphical

# Optional: tune VM boot log verbosity (default: quiet)
BOOTC_VM_LOG_LEVEL=quiet BUILD_IMAGE_TAG=local mise run run:vm:graphical
BOOTC_VM_LOG_LEVEL=normal BUILD_IMAGE_TAG=local mise run run:vm:graphical
BOOTC_VM_LOG_LEVEL=debug BUILD_IMAGE_TAG=local mise run run:vm:graphical

# Optional: disable injected serial kernel logs or fully customize injected kernel cmdline
BOOTC_VM_SERIAL_KERNEL_LOG=0 BUILD_IMAGE_TAG=local mise run run:vm:graphical
BOOTC_VM_KERNEL_CMDLINE='console=ttyS0 loglevel=7' BUILD_IMAGE_TAG=local mise run run:vm:graphical
```

Host-mutating workflow:

```bash
# Build the image and switch the local host via bootc
mise run host:upgrade
```

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
