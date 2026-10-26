#!/bin/sh
. /opt/Soft/install-local.sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1
echo "Устанавливаю Smart-Photo..."
echo
printf '%s' "Порт веб-интерфейса [8003]: "
IFS= read -r photo_port
photo_port=$(printf '%s' "$photo_port" | tr -cd '0-9')
if [ -z "$photo_port" ]; then
    photo_port=8003
fi
if [ "$photo_port" -lt 1 ] || [ "$photo_port" -gt 65535 ]; then
    echo "Неверный порт."
    exit 1
fi
echo
soft_install_order "$dir" order || exit 1
mkdir -p /opt/etc/smart-photo || exit 1
cfg=/opt/etc/smart-photo/config.json
if [ ! -f "$cfg" ]; then
    printf '{\n  "web_port": %s\n}\n' "$photo_port" > "$cfg"
elif grep -q '"web_port"' "$cfg"; then
    sed -i -E "s/\"web_port\"[[:space:]]*:[[:space:]]*[0-9]+/\"web_port\": $photo_port/" "$cfg"
else
    sed -i "s/{/{\n  \"web_port\": $photo_port,/" "$cfg"
fi
if [ -f /opt/etc/init.d/S99smart-photo ]; then
    sh /opt/etc/init.d/S99smart-photo restart >/dev/null 2>&1 || sh /opt/etc/init.d/S99smart-photo start >/dev/null 2>&1 || true
fi
echo "Smart-Photo установлен. Порт $photo_port"
exit 0
