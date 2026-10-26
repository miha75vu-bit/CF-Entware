#!/bin/sh
# Индекс локального фида /opt/Soft: Packages и Packages.gz.
root=/opt/Soft
out="$root/Packages"
tmp="/tmp/soft-index.$$"
rm -rf "$tmp"
mkdir -p "$tmp" || exit 1
: > "$out" || exit 1

find "$root" -type f -name '*.ipk' 2>/dev/null | sort | while IFS= read -r ipk; do
    [ -f "$ipk" ] || continue
    rel=${ipk#"$root"/}
    case "$rel" in
        Packages|Packages.gz|deps/*|*/deps/*) continue ;;
    esac
    rm -rf "$tmp/c" "$tmp/u"
    mkdir -p "$tmp/c" "$tmp/u" || continue
    if ! tar -xzf "$ipk" -C "$tmp/c" ./control.tar.gz 2>/dev/null; then
        tar -xzf "$ipk" -C "$tmp/c" control.tar.gz 2>/dev/null || continue
    fi
    ct=$(find "$tmp/c" -name 'control.tar.gz' -type f 2>/dev/null | head -n 1)
    [ -n "$ct" ] || continue
    tar -xzf "$ct" -C "$tmp/u" 2>/dev/null || continue
    ctrl=$(find "$tmp/u" -name control -type f 2>/dev/null | head -n 1)
    [ -n "$ctrl" ] || continue
    pkg=$(sed -n 's/^Package:[[:space:]]*//p' "$ctrl" | head -n 1 | tr -d '\r')
    ver=$(sed -n 's/^Version:[[:space:]]*//p' "$ctrl" | head -n 1 | tr -d '\r')
    [ -n "$pkg" ] || continue
    [ -n "$ver" ] || ver=0
    arch=$(sed -n 's/^Architecture:[[:space:]]*//p' "$ctrl" | head -n 1 | tr -d '\r')
    deps=$(sed -n 's/^Depends:[[:space:]]*//p' "$ctrl" | head -n 1 | tr -d '\r')
    desc=$(sed -n 's/^Description:[[:space:]]*//p' "$ctrl" | head -n 1 | tr -d '\r')
    size=$(wc -c < "$ipk" | tr -d ' \r')
    sum=$(sha256sum "$ipk" 2>/dev/null | awk '{print $1}')
    {
        echo "Package: $pkg"
        echo "Version: $ver"
        [ -n "$deps" ] && echo "Depends: $deps"
        [ -n "$arch" ] && echo "Architecture: $arch"
        echo "Filename: $rel"
        echo "Size: $size"
        [ -n "$sum" ] && echo "SHA256sum: $sum"
        [ -n "$desc" ] && echo "Description: $desc"
        echo
    } >> "$out"
done

gzip -c "$out" > "$root/Packages.gz" 2>/dev/null || gzip -c "$out" > "$root/Packages.gz"
rm -rf "$tmp"
exit 0
