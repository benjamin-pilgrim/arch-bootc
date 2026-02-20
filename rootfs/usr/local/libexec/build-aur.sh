#!/usr/bin/env bash
set -euo pipefail

packages_file="${1:-/tmp/packages-aur.txt}"

umask 022
install -d -m 755 "$HOME/cache/aur" "$HOME/cache/src" "$HOME/cache/build" "$HOME/cache/pkg"

pkg_files_list="$(mktemp)"
trap 'rm -f "$pkg_files_list"' EXIT

build_aur_pkg() {
    local pkg="$1"
    local repo_dir="$HOME/cache/aur/$pkg"
    local cached_pkg=""

    cached_pkg="$(find "$HOME/cache/pkg" -maxdepth 1 -type f -name "${pkg}-[0-9]*.pkg.tar.zst" ! -name "*-debug-*.pkg.tar.zst" | sort -V | tail -n 1 || true)"
    if [ -n "$cached_pkg" ]; then
        printf "%s\n" "$cached_pkg" >> "$pkg_files_list"
        return 0
    fi

    if [ -d "$repo_dir/.git" ]; then
        git -C "$repo_dir" fetch --depth 1 origin master
        git -C "$repo_dir" reset --hard origin/master
    else
        git clone --depth 1 --single-branch "https://aur.archlinux.org/${pkg}.git" "$repo_dir"
    fi

    (cd "$repo_dir" && makepkg -s)

    cached_pkg="$(find "$HOME/cache/pkg" -maxdepth 1 -type f -name "${pkg}-[0-9]*.pkg.tar.zst" ! -name "*-debug-*.pkg.tar.zst" | sort -V | tail -n 1 || true)"
    if [ -z "$cached_pkg" ]; then
        echo "requested package '$pkg' did not produce a package artifact" >&2
        exit 1
    fi
    printf "%s\n" "$cached_pkg" >> "$pkg_files_list"
}

while IFS= read -r pkg; do
    [ -z "$pkg" ] && continue
    [ "${pkg#\#}" != "$pkg" ] && continue
    build_aur_pkg "$pkg"
done < "$packages_file"

find "$HOME/cache/pkg" -maxdepth 1 -type f -name "*-debug-*.pkg.tar.zst" -delete
awk '!seen[$0]++' "$pkg_files_list" > "$HOME/cache/pkg/.install-list"
