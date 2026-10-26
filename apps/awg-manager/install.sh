#!/bin/sh
. /opt/Soft/install-local.sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1
echo "Устанавливаю AWG Manager..."
echo "Пакет берётся из архива."
echo
soft_install_order "$dir" order || exit 1
echo "AWG Manager установлен."
echo "Служба: /opt/etc/init.d/S99awg-manager {start|stop|restart|status}"
exit 0
