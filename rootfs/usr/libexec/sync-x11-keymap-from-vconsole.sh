#!/bin/sh
set -eu

dropin_dir="/run/hypr/override.d"
default_dropin="$dropin_dir/00-default.conf"
keyboard_dropin="$dropin_dir/20-system-keyboard.conf"

extract_localectl_field() {
    field="$1"
    printf '%s\n' "${2:-}" | sed -n "s/^[[:space:]]*$field:[[:space:]]*//p" | head -n 1
}

extract_x11conf_option() {
    key="$1"
    [ -r /etc/X11/xorg.conf.d/00-keyboard.conf ] || return 0
    sed -n "s/^[[:space:]]*Option[[:space:]]*\"$key\"[[:space:]]*\"\([^\"]*\)\"/\1/p" /etc/X11/xorg.conf.d/00-keyboard.conf | head -n 1
}

mkdir -p "$dropin_dir"
cat >"$default_dropin" <<'EOF'
# Runtime Hyprland override sentinel.
EOF

if ! command -v localectl >/dev/null 2>&1; then
    rm -f "$keyboard_dropin"
    exit 0
fi

status="$(localectl status 2>/dev/null || true)"
x11_layout="$(extract_localectl_field 'X11 Layout' "$status")"
x11_model="$(extract_localectl_field 'X11 Model' "$status")"
x11_variant="$(extract_localectl_field 'X11 Variant' "$status")"
x11_options="$(extract_localectl_field 'X11 Options' "$status")"
vc_keymap="$(extract_localectl_field 'VC Keymap' "$status")"

[ "$x11_layout" != "(unset)" ] || x11_layout=""

if [ -z "$x11_layout" ] && [ -n "$vc_keymap" ] && [ "$vc_keymap" != "(unset)" ]; then
    localectl set-keymap "$vc_keymap"
    status="$(localectl status 2>/dev/null || true)"
    x11_layout="$(extract_localectl_field 'X11 Layout' "$status")"
    x11_model="$(extract_localectl_field 'X11 Model' "$status")"
    x11_variant="$(extract_localectl_field 'X11 Variant' "$status")"
    x11_options="$(extract_localectl_field 'X11 Options' "$status")"
    [ "$x11_layout" != "(unset)" ] || x11_layout=""
fi

[ -n "$x11_layout" ] || x11_layout="$(extract_x11conf_option XkbLayout)"
[ -n "$x11_model" ] || x11_model="$(extract_x11conf_option XkbModel)"
[ -n "$x11_variant" ] || x11_variant="$(extract_x11conf_option XkbVariant)"
[ -n "$x11_options" ] || x11_options="$(extract_x11conf_option XkbOptions)"

if [ -n "$x11_layout" ] || [ -n "$x11_model" ] || [ -n "$x11_variant" ] || [ -n "$x11_options" ]; then
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
else
    rm -f "$keyboard_dropin"
fi
