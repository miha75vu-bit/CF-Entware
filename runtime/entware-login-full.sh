#!/bin/sh
case $- in
    *i*) ;;
    *) return 0 2>/dev/null || exit 0 ;;
esac
[ -t 0 ] || return 0 2>/dev/null || exit 0
[ -r /opt/root/custom-banner.sh ] && . /opt/root/custom-banner.sh
[ -f /opt/Soft/menu.sh ] || return 0 2>/dev/null || exit 0
sh /opt/Soft/menu.sh
return 0 2>/dev/null || exit 0
