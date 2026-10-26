#!/bin/sh
echo "Удаляю папку установщиков, меню и локальный фид..."
rm -rf /opt/Soft 2>/dev/null || true
rm -f /opt/etc/opkg/soft.conf 2>/dev/null || true
rm -f /opt/var/opkg-lists/soft /opt/var/opkg-lists/soft.gz 2>/dev/null || true
rm -f /opt/lib/opkg/lists/soft /opt/usr/lib/opkg/lists/soft 2>/dev/null || true
if [ -f /opt/etc/profile ]; then
    sed -i '/entware-login/d' /opt/etc/profile 2>/dev/null || true
fi
rm -f /opt/usr/local/sbin/entware-login.sh 2>/dev/null || true
rm -f /opt/usr/local/sbin/soft-index.sh 2>/dev/null || true
echo "Готово. Дополнительные фиды и штатный профиль на месте."
rm -f /opt/usr/local/sbin/entware-remove-soft.sh 2>/dev/null || true
exit 0
