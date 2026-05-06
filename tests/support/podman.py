from __future__ import annotations

import subprocess

from host_ops import podman_cmd


class PodmanImage:
    def __init__(self, image_ref: str) -> None:
        self.image_ref = image_ref

    def run(
        self,
        args: list[str],
        *,
        entrypoint: str = "sh",
        check: bool = True,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            podman_cmd(["run", "--rm", "--entrypoint", entrypoint, self.image_ref, *args]),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if check:
            assert result.returncode == 0, command_failure(result)
        return result

    def shell(self, script: str, *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return self.run(["-lc", script], check=check, timeout=timeout)

    def grep(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(args, entrypoint="grep", check=check)


def command_failure(result: subprocess.CompletedProcess[str]) -> str:
    return (
        f"command failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
