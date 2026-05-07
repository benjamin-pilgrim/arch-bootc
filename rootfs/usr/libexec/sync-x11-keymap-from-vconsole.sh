#!/bin/sh
set -eu

dropin_dir="/run/hypr/override.d"
default_dropin="$dropin_dir/00-default.conf"
keyboard_dropin="$dropin_dir/20-system-keyboard.conf"
x11conf="/etc/X11/xorg.conf.d/00-keyboard.conf"

x11_layout=""
x11_model=""
x11_variant=""
x11_options=""
vc_keymap=""
localectl_status=""

write_default_dropin() {
    mkdir -p "$dropin_dir"
    cat >"$default_dropin" <<'EOF'
# Runtime Hyprland override sentinel.
EOF
}

localectl_field() {
    field="$1"
    printf '%s\n' "$localectl_status" | sed -n "s/^[[:space:]]*$field:[[:space:]]*//p" | head -n 1
}

normalize_field() {
    value="${1:-}"
    if [ "$value" = "(unset)" ]; then
        printf '\n'
        return
    fi
    printf '%s\n' "$value"
}

refresh_localectl_status() {
    localectl_status="$(localectl status 2>/dev/null || true)"
    x11_layout="$(normalize_field "$(localectl_field 'X11 Layout')")"
    x11_model="$(normalize_field "$(localectl_field 'X11 Model')")"
    x11_variant="$(normalize_field "$(localectl_field 'X11 Variant')")"
    x11_options="$(normalize_field "$(localectl_field 'X11 Options')")"
    vc_keymap="$(normalize_field "$(localectl_field 'VC Keymap')")"
}

read_x11conf_option() {
    key="$1"
    [ -r "$x11conf" ] || return 0
    sed -n "s/^[[:space:]]*Option[[:space:]]*\"$key\"[[:space:]]*\"\([^\"]*\)\"/\1/p" "$x11conf" | head -n 1
}

fill_from_x11conf() {
    [ -n "$x11_layout" ] || x11_layout="$(read_x11conf_option XkbLayout)"
    [ -n "$x11_model" ] || x11_model="$(read_x11conf_option XkbModel)"
    [ -n "$x11_variant" ] || x11_variant="$(read_x11conf_option XkbVariant)"
    [ -n "$x11_options" ] || x11_options="$(read_x11conf_option XkbOptions)"
}

write_keyboard_dropin() {
    write_default_dropin
    tmp_keyboard_dropin="$(mktemp "$dropin_dir/.20-system-keyboard.conf.XXXXXX")"
    cat >"$tmp_keyboard_dropin" <<EOF
# Generated from system keyboard defaults.
# Adjust the system keymap with localectl/systemd-firstboot instead of editing this file.
input {
EOF
    [ -n "$x11_layout" ] && printf '    kb_layout = %s\n' "$x11_layout" >>"$tmp_keyboard_dropin"
    [ -n "$x11_model" ] && printf '    kb_model = %s\n' "$x11_model" >>"$tmp_keyboard_dropin"
    [ -n "$x11_variant" ] && printf '    kb_variant = %s\n' "$x11_variant" >>"$tmp_keyboard_dropin"
    [ -n "$x11_options" ] && printf '    kb_options = %s\n' "$x11_options" >>"$tmp_keyboard_dropin"
    cat >>"$tmp_keyboard_dropin" <<'EOF'
}
EOF
    chmod 0644 "$tmp_keyboard_dropin"
    mv "$tmp_keyboard_dropin" "$keyboard_dropin"
}

write_default_dropin

if ! command -v localectl >/dev/null 2>&1; then
    rm -f "$keyboard_dropin"
    exit 0
fi

refresh_localectl_status

if [ -z "$x11_layout" ] && [ -n "$vc_keymap" ]; then
    localectl set-keymap "$vc_keymap"
    refresh_localectl_status
fi

fill_from_x11conf

if [ -n "$x11_layout" ] || [ -n "$x11_model" ] || [ -n "$x11_variant" ] || [ -n "$x11_options" ]; then
    write_keyboard_dropin
else
    rm -f "$keyboard_dropin"
fi
