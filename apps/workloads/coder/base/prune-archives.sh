#!/bin/sh
# Called only after all workspace backup transfers have succeeded.
set -eu
export LC_ALL=C
umask 077

archive_root=${1:?Archive root is required}
case "$archive_root" in
  */archive) ;;
  *) echo 'Refusing to prune outside an archive root' >&2; exit 1 ;;
esac

now=$(date -u +%s)
cutoff_epoch=$((now - 14 * 86400))
prefixes=$(mktemp)
trap 'rm -f "$prefixes"' EXIT

# One shallow listing; do not inspect object modification times.
rclone lsf "$archive_root" --dirs-only --max-depth 1 --log-level ERROR > "$prefixes"
purged=0
retained_unknown=0
while IFS= read -r prefix; do
  case "$prefix" in
    ????-??-??T??-??-??Z/) ;;
    *) retained_unknown=$((retained_unknown + 1)); continue ;;
  esac
  name=${prefix%/}
  case "$name" in
    *[!0-9TZ-]*) retained_unknown=$((retained_unknown + 1)); continue ;;
  esac
  # Round-trip validation also rejects impossible dates and malformed names.
  readable=$(printf '%s' "$name" | sed 's/T/ /;s/\(..\)-\(..\)-\(..\)Z$/\1:\2:\3/')
  prefix_epoch=$(date -u -d "$readable" +%s 2>/dev/null) || prefix_epoch=
  if [ -z "$prefix_epoch" ]; then
    retained_unknown=$((retained_unknown + 1))
    continue
  fi
  canonical=$(date -u -d "@$prefix_epoch" +%Y-%m-%dT%H-%M-%SZ 2>/dev/null) || canonical=
  if [ "$canonical" != "$name" ]; then
    retained_unknown=$((retained_unknown + 1))
    continue
  fi
  if [ "$prefix_epoch" -lt "$cutoff_epoch" ]; then
    # The exact validated timestamp is appended below archive/, never current/.
    rclone purge "$archive_root/$name" --log-level ERROR
    purged=$((purged + 1))
  fi
done < "$prefixes"
printf 'Archive retention complete: %s expired prefixes purged; %s unrecognized prefixes retained\n' "$purged" "$retained_unknown"
