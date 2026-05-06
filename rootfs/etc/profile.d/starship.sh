# Use the image-managed Starship prompt unless the user selected another config.
export STARSHIP_CONFIG="${STARSHIP_CONFIG:-/etc/starship.toml}"

case "$-" in
    *i*) ;;
    *) return 0 ;;
esac

command -v starship >/dev/null 2>&1 || return 0

if [ -n "${BASH_VERSION:-}" ]; then
    eval "$(starship init bash)"
elif [ -n "${ZSH_VERSION:-}" ]; then
    eval "$(starship init zsh)"
fi
