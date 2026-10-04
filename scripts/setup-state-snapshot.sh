#!/usr/bin/env bash
# setup-state-snapshot.sh: State snapshot/restore around OTA (P11-9).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="$REPO_ROOT/var/state-snapshots"
mkdir -p "$SNAPSHOT_DIR"

cmd="${1:-}"

case "$cmd" in
  snapshot)
    ts="$(date +%Y%m%d-%H%M%S)"
    target="$SNAPSHOT_DIR/pre-ota-$ts"
    mkdir -p "$target"
    # Copy settings, library index, history, user state
    [ -f "$REPO_ROOT/config/settings.json" ] && cp "$REPO_ROOT/config/settings.json" "$target/"
    [ -f "$REPO_ROOT/var/library/library.db" ] && cp "$REPO_ROOT/var/library/library.db" "$target/"
    [ -f "$REPO_ROOT/var/user/user.db" ] && cp "$REPO_ROOT/var/user/user.db" "$target/"
    [ -f "$REPO_ROOT/config/tv.conf" ] && cp "$REPO_ROOT/config/tv.conf" "$target/"
    echo "State snapshot saved to $target"
    ;;
  restore)
    latest="$(ls -1d "$SNAPSHOT_DIR"/pre-ota-* 2>/dev/null | sort | tail -1)"
    if [ -z "$latest" ] || [ ! -d "$latest" ]; then
      echo "No snapshot to restore" >&2
      exit 1
    fi
    [ -f "$latest/settings.json" ] && cp "$latest/settings.json" "$REPO_ROOT/config/"
    [ -f "$latest/library.db" ] && cp "$latest/library.db" "$REPO_ROOT/var/library/"
    [ -f "$latest/user.db" ] && cp "$latest/user.db" "$REPO_ROOT/var/user/"
    [ -f "$latest/tv.conf" ] && cp "$latest/tv.conf" "$REPO_ROOT/config/"
    echo "State restored from $latest"
    ;;
  *)
    echo "Usage: $0 {snapshot|restore}" >&2
    exit 1
    ;;
esac
