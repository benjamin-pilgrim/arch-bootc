# Opinionated Arch Bootc Image

## Development Tasks

This repo uses `mise` for tool + task management.

```bash
mise trust
mise install
mise tasks ls
```

Examples:

```bash
# Build image (defaults to arch-bootc:latest)
mise run build-containerfile

# Run structure tests against a local tag
BUILD_IMAGE_NAME=arch-bootc BUILD_IMAGE_TAG=local mise run test-structure

# Run container smoke tests against a local tag
BUILD_IMAGE_NAME=arch-bootc BUILD_IMAGE_TAG=local mise run test-smoke-container

# Run VM smoke tests against a booted guest over SSH
BOOTC_VM_SSH='root@127.0.0.1 -p 2222' mise run test-smoke-vm

# Optional: if SSH user is non-root, prefix privileged commands
BOOTC_VM_ROOT_PREFIX='sudo -n' BOOTC_VM_SSH='user@vm' mise run test-smoke-vm

# Boot local bootable.img with qemu and run VM smoke tests end-to-end
# (requires qemu-system-x86_64; defaults to SSH on localhost:2222 as root)
mise run test-smoke-vm-local

# Optional: override image tag used by vm-local flow (defaults to local)
BUILD_IMAGE_TAG=latest mise run test-smoke-vm-local

# Optional: choose a different forwarded SSH port or user
BOOTC_VM_SSH_PORT=2223 BOOTC_VM_SSH_USER=root mise run test-smoke-vm-local

# Optional: disable systemd-ssh-generator path and provide your own SSH setup
BOOTC_VM_USE_SYSTEMD_SSH_GENERATOR=0 mise run test-smoke-vm-local

# Optional: customize the generated SSH listener for systemd-ssh-generator
BOOTC_VM_SYSTEMD_SSH_LISTEN='0.0.0.0:22' mise run test-smoke-vm-local

# Optional: tune VM boot log verbosity (default: quiet)
BOOTC_VM_LOG_LEVEL=quiet mise run test-smoke-vm-local
BOOTC_VM_LOG_LEVEL=normal mise run test-smoke-vm-local
BOOTC_VM_LOG_LEVEL=debug mise run test-smoke-vm-local

# Optional: disable injected serial kernel logs or fully customize injected kernel cmdline
BOOTC_VM_SERIAL_KERNEL_LOG=0 mise run test-smoke-vm-local
BOOTC_VM_KERNEL_CMDLINE='console=ttyS0 loglevel=7' mise run test-smoke-vm-local
```
