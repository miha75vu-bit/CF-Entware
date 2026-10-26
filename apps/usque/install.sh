#!/bin/sh
echo
echo "Usque — неофициальный клиент Cloudflare WARP (протокол MASQUE) для Keenetic."
echo "Создаёт интерфейс usque, через который можно пускать выбранный трафик."
echo
echo "Для регистрации и проксирования добавьте в обход:"
echo "  api.cloudflareclient.com"
echo "  consumer-masque.cloudflareclient.com"
echo
printf '%s' "Enter — продолжить, 0 — назад: "
IFS= read -r usque_ans
usque_ans=$(printf '%s' "$usque_ans" | tr -d '\r')
if [ "$usque_ans" = "0" ]; then
    exit 0
fi
echo
echo "Устанавливаю Usque (usque-keenetic)..."
echo "Выполняются команды установки. Не прерывайте процесс."
echo
mkdir -p /opt/etc/opkg || exit 1
echo "src/gz usque-keenetic https://side-effect-tm.github.io/usque-keenetic/all" > /opt/etc/opkg/usque-keenetic.conf
opkg update && opkg install usque-keenetic
rc=$?
echo
if [ "$rc" -ne 0 ]; then
    echo "Установка Usque завершилась с ошибкой (код $rc)."
    exit "$rc"
fi
echo "Пакет Usque установлен."
if [ -f /opt/etc/usque/session.conf ]; then
    echo "Регистрация клиента Cloudflare прошла успешно."
else
    echo
    echo "Регистрация клиента Cloudflare не выполнена (нет /opt/etc/usque/session.conf)."
    echo "Добавьте в обход и попробуйте снова:"
    echo "  api.cloudflareclient.com"
    echo "  consumer-masque.cloudflareclient.com"
    echo "  zt-masque.cloudflareclient.com"
    echo "  consumer-masque-proxy.cloudflareclient.com"
    echo "  cloudflareaccess.com"
    echo "  162.159.198.1"
    echo "  162.159.198.2"
    echo
    echo "Затем:"
    echo "  /opt/etc/init.d/S51usque start"
    echo "или:"
    echo "  usque register --accept-tos --config /opt/etc/usque/session.conf"
fi
exit 0
