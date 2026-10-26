#!/bin/sh
# Установка пакетов из папки программы. Списки order и web-order — пути относительно папки.

soft_install_order() {
    _dir=$1
    _list=$2
    if [ ! -f "$_dir/$_list" ]; then
        echo "Нет списка пакетов: $_dir/$_list"
        return 1
    fi
    while IFS= read -r _rel || [ -n "$_rel" ]; do
        _rel=$(printf '%s' "$_rel" | tr -d '\r')
        [ -n "$_rel" ] || continue
        case "$_rel" in
            \#*) continue ;;
        esac
        if [ ! -f "$_dir/$_rel" ]; then
            echo "Нет файла пакета: $_dir/$_rel"
            return 1
        fi
        echo "Ставлю $(basename "$_rel")..."
        if ! opkg install "$_dir/$_rel"; then
            echo "Не удалось поставить $_rel"
            return 1
        fi
    done < "$_dir/$_list"
    if [ -x /opt/usr/local/sbin/soft-index.sh ]; then
        /opt/usr/local/sbin/soft-index.sh || true
    fi
    return 0
}

soft_reinstall_lighttpd() {
    _dir=$1
    _lt=""
    for _f in "$_dir"/deps/lighttpd_*.ipk "$_dir"/lighttpd_*.ipk; do
        [ -f "$_f" ] || continue
        case "$(basename "$_f")" in
            lighttpd_*) _lt=$_f; break ;;
        esac
    done
    if [ -z "$_lt" ]; then
        echo "В архиве нет пакета lighttpd."
        return 1
    fi
    echo "Восстанавливаю lighttpd..."
    if ! opkg install --force-reinstall "$_lt"; then
        echo "Не удалось переустановить lighttpd."
        return 1
    fi
    if [ ! -e /opt/etc/init.d/S80lighttpd ]; then
        echo "Нет /opt/etc/init.d/S80lighttpd."
        return 1
    fi
    /opt/etc/init.d/S80lighttpd restart >/dev/null 2>&1 || true
    return 0
}
