#!/usr/bin/env python3
import json
import os
import pwd
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


PACKAGES_FILE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/packages-aur.txt")
HOME = Path(os.environ.get("AUR_BUILD_HOME", "/home/makepkg"))
CACHE_AUR = HOME / "cache" / "aur"
CACHE_SRC = HOME / "cache" / "src"
CACHE_BUILD = HOME / "cache" / "build"
CACHE_PKG = HOME / "cache" / "pkg"
CACHE_XDG = HOME / "cache" / "xdg"
CACHE_GO = HOME / "cache" / "go-build"
INSTALL_LIST = CACHE_PKG / ".install-list"
AUR_RPC = "https://aur.archlinux.org/rpc/v5"
DEP_SPLIT_RE = re.compile(r"[<>=]+")


def run(cmd, *, cwd=None, user=None, capture=False, check=True, env_extra=None):
    actual = cmd
    if user:
        actual = ["runuser", "-u", user, "--", *cmd]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        actual,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
        env=env,
    )


def out(cmd, *, cwd=None, user=None):
    return run(cmd, cwd=cwd, user=user, capture=True).stdout.strip()


def dep_name(dep_expr):
    return DEP_SPLIT_RE.split(dep_expr, 1)[0].strip()


def ensure_dirs():
    makepkg = pwd.getpwnam("makepkg")
    for path in (CACHE_AUR, CACHE_SRC, CACHE_BUILD, CACHE_PKG, CACHE_XDG, CACHE_GO):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, makepkg.pw_uid, makepkg.pw_gid)
    os.umask(0o022)
    os.environ.setdefault("RUST_MIN_STACK", "16777216")


def ensure_makepkg_owned(path):
    makepkg = pwd.getpwnam("makepkg")
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, makepkg.pw_uid, makepkg.pw_gid)


def pacman_dep_satisfied(dep_expr):
    result = run(["pacman", "-T", dep_expr], capture=True, check=False)
    return result.returncode == 0 and result.stdout.strip() == ""


def pacman_official_available(pkg_name):
    global official_repo_packages
    if official_repo_packages is None:
        official_repo_packages = set(out(["bash", "-lc", "pacman -Sy >/dev/null && pacman -Ssq"]).splitlines())
    return pkg_name in official_repo_packages


def install_official(packages):
    pkgs = sorted(set(packages))
    if pkgs:
        run(["pacman", "-Sy", "--noconfirm", "--needed", *pkgs])


def aur_rpc_json(url):
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def aur_info(name):
    query = urllib.parse.urlencode([("arg[]", name)])
    data = aur_rpc_json(f"{AUR_RPC}/info?{query}")
    results = data.get("results", [])
    return results[0] if results else None


def aur_search_provides(symbol):
    query = urllib.parse.quote(symbol)
    data = aur_rpc_json(f"{AUR_RPC}/search/{query}?by=provides")
    return data.get("results", [])


class RepoInfo:
    def __init__(self, repo_name, repo_dir, pkgbase, pkgnames, provides, deps):
        self.repo_name = repo_name
        self.repo_dir = repo_dir
        self.pkgbase = pkgbase
        self.pkgnames = pkgnames
        self.provides = provides
        self.deps = deps

    @property
    def symbols(self):
        symbols = set(self.pkgnames)
        symbols.update(dep_name(item) for item in self.provides)
        return symbols


repo_cache = {}
provider_cache = {}
symbol_to_repo = {}
official_needed = set()
top_level_repos = []
official_repo_packages = None


def remote_default_branch(repo_name):
    url = f"https://aur.archlinux.org/{repo_name}.git"
    lines = out(["git", "ls-remote", "--symref", url, "HEAD"], user="makepkg").splitlines()
    for line in lines:
        if not line.startswith("ref: ") or "\tHEAD" not in line:
            continue
        ref = line.split("\t", 1)[0].split(" ", 1)[1].strip()
        return ref.rsplit("/", 1)[-1]
    heads = out(["git", "ls-remote", "--heads", url], user="makepkg").splitlines()
    branches = []
    for line in heads:
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[1].startswith("refs/heads/"):
            continue
        branches.append(parts[1].rsplit("/", 1)[-1])
    if "master" in branches:
        return "master"
    if "main" in branches:
        return "main"
    if len(branches) == 1:
        return branches[0]
    raise RuntimeError(f"unable to determine default branch for {repo_name}")


def aur_repo_name(pkg_name):
    info = aur_info(pkg_name)
    if not info:
        return None
    return info.get("PackageBase") or info["Name"]


def update_repo(repo_name):
    repo_dir = CACHE_AUR / repo_name
    branch = remote_default_branch(repo_name)
    if (repo_dir / ".git").exists():
        run(["git", "-C", str(repo_dir), "fetch", "--depth", "1", "origin", branch], user="makepkg")
        run(["git", "-C", str(repo_dir), "checkout", "-B", branch, f"origin/{branch}"], user="makepkg")
    else:
        run(
            ["git", "clone", "--depth", "1", "--single-branch", "--branch", branch, f"https://aur.archlinux.org/{repo_name}.git", str(repo_dir)],
            user="makepkg",
        )
    srcinfo = repo_dir / ".SRCINFO"
    generated = out(["bash", "-lc", "makepkg --printsrcinfo"], cwd=repo_dir, user="makepkg")
    srcinfo.write_text(generated)
    return repo_dir


def parse_srcinfo(repo_name, repo_dir):
    pkgbase = None
    pkgnames = []
    provides = []
    deps = []
    current_pkg = None
    srcinfo = (repo_dir / ".SRCINFO").read_text().splitlines()
    for raw in srcinfo:
        line = raw.strip()
        if not line or " = " not in line:
            continue
        key, value = [part.strip() for part in line.split(" = ", 1)]
        if key == "pkgbase":
            pkgbase = value
            current_pkg = None
        elif key == "pkgname":
            pkgnames.append(value)
            current_pkg = value
        elif key in {"depends", "makedepends", "checkdepends"}:
            deps.append(value)
        elif key == "provides":
            provides.append(value)
    if not pkgbase:
        raise RuntimeError(f"failed to parse .SRCINFO for {repo_name}")
    return RepoInfo(repo_name, repo_dir, pkgbase, pkgnames, provides, deps)


def load_repo(repo_name):
    if repo_name in repo_cache:
        return repo_cache[repo_name]
    repo_dir = update_repo(repo_name)
    info = parse_srcinfo(repo_name, repo_dir)
    repo_cache[repo_name] = info
    for symbol in info.symbols:
        symbol_to_repo.setdefault(symbol, repo_name)
    return info


def select_provider(dep_expr):
    dep = dep_name(dep_expr)
    if dep in provider_cache:
        return provider_cache[dep]
    if dep in symbol_to_repo:
        provider_cache[dep] = symbol_to_repo[dep]
        return provider_cache[dep]

    exact = aur_info(dep)
    if exact:
        provider_cache[dep] = exact.get("PackageBase") or exact["Name"]
        return provider_cache[dep]

    candidates = aur_search_provides(dep)
    if len(candidates) == 1:
        provider_cache[dep] = candidates[0].get("PackageBase") or candidates[0]["Name"]
        return provider_cache[dep]

    matches = []
    for candidate in candidates:
        candidate_name = candidate["Name"]
        candidate_info = aur_info(candidate_name) or candidate
        candidate_repo = candidate_info.get("PackageBase") or candidate_name
        provides = candidate_info.get("Provides") or []
        if candidate_name == dep or any(dep_name(item) == dep for item in provides):
            matches.append(candidate_repo)

    unique = sorted(set(matches))
    if len(unique) == 1:
        provider_cache[dep] = unique[0]
        return provider_cache[dep]
    if len(unique) > 1:
        preferred = [name for name in unique if not name.endswith("-git")]
        choice = preferred[0] if len(preferred) == 1 else unique[0]
        provider_cache[dep] = choice
        return provider_cache[dep]
    return None


def resolve_repo(repo_name, resolved, visiting):
    if repo_name in resolved:
        return
    if repo_name in visiting:
        raise RuntimeError(f"AUR dependency cycle detected at {repo_name}")
    visiting.add(repo_name)
    info = load_repo(repo_name)
    for dependency in info.deps:
        if pacman_dep_satisfied(dependency):
            continue
        symbol = dep_name(dependency)
        if pacman_official_available(symbol):
            official_needed.add(symbol)
            continue
        provider = select_provider(symbol)
        if provider:
            resolve_repo(provider, resolved, visiting)
            continue
        raise RuntimeError(f"unable to resolve dependency '{dependency}' for {repo_name}")
    visiting.remove(repo_name)
    resolved.append(repo_name)


def repo_head(repo_dir):
    return out(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], user="makepkg")


def find_artifacts(pkg_names):
    artifacts = []
    if not CACHE_PKG.exists():
        return artifacts
    for path in sorted(CACHE_PKG.glob("*.pkg.tar.zst")):
        if "-debug-" in path.name:
            continue
        pkg_name = out(["pacman", "-Qp", str(path)]).split()[0]
        if pkg_name in pkg_names:
            artifacts.append(path)
    return artifacts


def build_repo(info):
    stamp_file = CACHE_PKG / f".{info.repo_name}.aur-head"
    head = repo_head(info.repo_dir)
    artifacts = find_artifacts(info.pkgnames)
    if stamp_file.exists() and stamp_file.read_text().strip() == head and len(artifacts) >= len(info.pkgnames):
        return artifacts

    run(
        ["bash", "-lc", "makepkg -sf --noconfirm --needed"],
        cwd=info.repo_dir,
        user="makepkg",
        env_extra={
            "AUR_BUILD_HOME": str(HOME),
            "XDG_CACHE_HOME": str(CACHE_XDG),
            "GOCACHE": str(CACHE_GO),
        },
    )
    artifacts = find_artifacts(info.pkgnames)
    if len(artifacts) < len(info.pkgnames):
        raise RuntimeError(f"repo '{info.repo_name}' did not produce all expected artifacts")
    stamp_file.write_text(f"{head}\n")
    return artifacts


def install_artifacts(artifacts):
    run(["pacman", "-U", "--noconfirm", *[str(path) for path in artifacts]])


def cleanup_path(path):
    if path.exists():
        run(["rm", "-rf", str(path)])


def cleanup_after_install(info, artifacts):
    for artifact in artifacts:
        cleanup_path(artifact)

    cleanup_path(CACHE_BUILD / info.repo_name)
    cleanup_path(info.repo_dir / "pkg")
    cleanup_path(info.repo_dir / "src")

    # These caches can grow very quickly for Go/Rust-heavy AUR packages.
    cleanup_path(CACHE_GO)
    cleanup_path(CACHE_XDG)
    ensure_makepkg_owned(CACHE_GO)
    ensure_makepkg_owned(CACHE_XDG)


def read_requested_repos():
    repos = []
    for raw in PACKAGES_FILE.read_text().splitlines():
        pkg = raw.strip()
        if not pkg or pkg.startswith("#"):
            continue
        repo_name = aur_repo_name(pkg)
        if not repo_name:
            raise RuntimeError(f"unable to resolve requested AUR package '{pkg}'")
        repos.append(repo_name)
    return repos


def main():
    ensure_dirs()
    global top_level_repos
    top_level_repos = read_requested_repos()

    resolved = []
    for repo_name in top_level_repos:
        resolve_repo(repo_name, resolved, set())

    install_official(official_needed)

    seen = set()
    for repo_name in resolved:
        if repo_name in seen:
            continue
        seen.add(repo_name)
        info = load_repo(repo_name)
        artifacts = build_repo(info)
        install_artifacts(artifacts)
        cleanup_after_install(info, artifacts)

    run(["find", str(CACHE_PKG), "-maxdepth", "1", "-type", "f", "-name", "*-debug-*.pkg.tar.zst", "-delete"])
    INSTALL_LIST.write_text("")


if __name__ == "__main__":
    main()
