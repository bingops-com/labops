#!/bin/sh
set -eu
umask 077
root=r2:bingops-cnpg-labprod/affine-files/snapshots
stamp=$(cat /backup/stamp)
test -s /backup/affine.tar.gz
# One immutable archive per run; keep upload integrity checks enabled.
rclone copyto /backup/affine.tar.gz "$root/$stamp.tar.gz" --checksum --no-traverse --log-level ERROR

cutoff=$(($(date -u +%s) - 14 * 86400))
list=$(mktemp)
trap 'rm -f "$list"' EXIT
rclone lsf "$root" --files-only --max-depth 1 --log-level ERROR > "$list"
removed=0
unknown=0
while IFS= read -r file; do
  case "$file" in
    ????-??-??T??-??-??Z.tar.gz) ;;
    *) unknown=$((unknown + 1)); continue ;;
  esac
  name=${file%.tar.gz}
  case "$name" in *[!0-9TZ-]*) unknown=$((unknown + 1)); continue ;; esac
  readable=$(printf '%s' "$name" | sed 's/T/ /;s/\(..\)-\(..\)-\(..\)Z$/\1:\2:\3/')
  epoch=$(date -u -d "$readable" +%s 2>/dev/null) || epoch=
  if [ -z "$epoch" ]; then unknown=$((unknown + 1)); continue; fi
  canonical=$(date -u -d "@$epoch" +%Y-%m-%dT%H-%M-%SZ 2>/dev/null) || canonical=
  if [ "$canonical" != "$name" ]; then unknown=$((unknown + 1)); continue; fi
  if [ "$epoch" -lt "$cutoff" ]; then
    rclone deletefile "$root/$file" --log-level ERROR
    removed=$((removed + 1))
  fi
done < "$list"
printf 'AFFiNE backup uploaded; %s expired archives deleted; %s unknown names retained\n' "$removed" "$unknown"
