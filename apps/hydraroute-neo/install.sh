#!/bin/sh
. /opt/Soft/install-local.sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1
echo "Устанавливаю HydraRoute Neo..."
echo "Пакеты берутся из архива."
echo
soft_install_order "$dir" order || exit 1
echo "HydraRoute Neo установлен."
exit 0
