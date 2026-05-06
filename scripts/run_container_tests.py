#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys

from host_ops import BASE_DIR


def main() -> int:
    return subprocess.run([sys.executable, "-m", "pytest", "-m", "container", *sys.argv[1:]], cwd=BASE_DIR).returncode


if __name__ == "__main__":
    raise SystemExit(main())
