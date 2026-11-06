#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 ]] || { printf 'Aufruf: bash 02-lan-einstellen.sh DECK_LAN_IPV4\n' >&2; exit 2; }
python3 "$(dirname "$0")/configure_local.py" "$HOME/steamdeck-homeserver" "$1"
"$HOME/steamdeck-homeserver/bin/caddy" validate --config "$HOME/steamdeck-homeserver/config/Caddyfile" --adapter caddyfile
