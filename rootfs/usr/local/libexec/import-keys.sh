#!/usr/bin/env bash
set -euo pipefail

keys_json="${1:-/tmp/keys.json}"

umask 022
export GNUPGHOME="${HOME}/.gnupg"
install -d -m 700 "$GNUPGHOME"

while IFS= read -r key_entry; do
    [ -z "$key_entry" ] && continue

    key_json="$(printf "%s" "$key_entry" | base64 -d)"
    key_name="$(printf "%s" "$key_json" | jq -r '.key')"
    key_url="$(printf "%s" "$key_json" | jq -r '.value.url // empty')"
    key_fpr_expected="$(printf "%s" "$key_json" | jq -r '.value.fingerprint // empty')"

    if [ -z "$key_url" ] || [ -z "$key_fpr_expected" ]; then
        echo "missing key metadata for $key_name" >&2
        exit 1
    fi

    key_file="$(mktemp)"
    curl -fsSL "$key_url" -o "$key_file"
    key_fpr_actual="$(gpg --show-keys --with-colons "$key_file" | awk -F: '$1=="fpr"{print $10; exit}')"

    if [ "$key_fpr_actual" != "$key_fpr_expected" ]; then
        echo "fingerprint mismatch for $key_name" >&2
        rm -f "$key_file"
        exit 1
    fi

    gpg --import "$key_file"
    rm -f "$key_file"
done < <(jq -r 'to_entries[]? | @base64' "$keys_json")
