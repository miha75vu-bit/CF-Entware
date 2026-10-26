#!/bin/sh
. /opt/Soft/install-local.sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1
echo "Устанавливаю web4static..."
echo "Пакеты берутся из архива."
echo
soft_install_order "$dir" order || exit 1
soft_reinstall_lighttpd "$dir" || exit 1
echo "web4static установлен. Порт :99"
exit 0
