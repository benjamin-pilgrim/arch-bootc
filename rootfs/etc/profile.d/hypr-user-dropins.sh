# Ensure Hypr user drop-ins are available for existing users.
# This is idempotent and does not overwrite user-managed files.

[ -n "${HOME:-}" ] || return 0

cfg_home="${XDG_CONFIG_HOME:-$HOME/.config}"
hypr_dir="$cfg_home/hypr"
main_cfg="$hypr_dir/hyprland.conf"
dropin_dir="$hypr_dir/hyprland.conf.d"
sentinel="$dropin_dir/00-default.conf"

mkdir -p "$dropin_dir"

if [ ! -e "$sentinel" ]; then
    cat >"$sentinel" <<'EOF'
# User Hyprland drop-in sentinel.
# Add additional files in this directory to extend your config.
EOF
fi

if [ ! -e "$main_cfg" ]; then
    cat >"$main_cfg" <<'EOF'
source = $XDG_CONFIG_HOME/hypr/hyprland.conf.d/*.conf
EOF
elif ! grep -Eq 'hyprland\.conf\.d/\*\.conf' "$main_cfg"; then
    cat >>"$main_cfg" <<'EOF'

# User Hyprland drop-ins.
source = $XDG_CONFIG_HOME/hypr/hyprland.conf.d/*.conf
EOF
fi
