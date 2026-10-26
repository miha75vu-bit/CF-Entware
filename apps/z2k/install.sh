#!/bin/sh
echo "Устанавливаю z2k..."
echo "Выполняется официальный скрипт установки. Не прерывайте процесс."
echo
{ curl --resolve raw.githubusercontent.com:443:213.176.74.63 -fsSL https://raw.githubusercontent.com/necronicle/z2k/z2k-enhanced/z2k.sh || curl -fsSL https://raw.githubusercontent.com/necronicle/z2k/z2k-enhanced/z2k.sh; } | sh
exit $?
