#!/bin/sh
case $- in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac
[ -t 0 ] || return 0 2>/dev/null || exit 0
[ -r /opt/root/custom-banner.sh ] && . /opt/root/custom-banner.sh

echo
echo "KeenSnap — резервное копирование для оригинальной прошивки Keenetic / Netcraze"
echo "KeenKit — резервное копирование для портированной прошивки на роутер другого производителя"
echo "Офлайн ставятся один или оба сразу при первой установке Flashkeen."
echo

_ipk=""
for _f in /opt/usr/local/flashkeen/*.ipk; do
    [ -f "$_f" ] || continue
    _ipk=$_f
    break
done
if [ -n "$_ipk" ]; then
    echo "Устанавливаю Flashkeen..."
    if ! opkg install "$_ipk"; then
        echo "Не удалось установить Flashkeen. При следующем входе попытка повторится."
        return 0 2>/dev/null || exit 1
    fi
    rm -f "$_ipk" 2>/dev/null || true
fi

if [ -f /opt/etc/profile ]; then
    sed -i '/entware-login/d' /opt/etc/profile 2>/dev/null || true
fi

if [ -x /opt/bin/flashkeen ]; then
    /opt/bin/flashkeen
fi
return 0 2>/dev/null || exit 0
