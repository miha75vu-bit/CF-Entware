#!/bin/sh
. /opt/Soft/install-local.sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1

echo
echo "Будет установлена NFQWS 2 Keenetic."
echo "Установить вместе с ним веб-интерфейс?"
echo
echo "1) Да, установить и веб-интерфейс"
echo "0) Нет, только NFQWS 2 Keenetic"
echo
printf '%s' "Ваш выбор: "
IFS= read -r web_ans
web_ans=$(printf '%s' "$web_ans" | tr -d '\r')
install_web=0
case "$web_ans" in
    1) install_web=1 ;;
    0) install_web=0 ;;
    *)
        echo "Неверный выбор. Установка отменена."
        exit 1
        ;;
esac

echo
echo "Устанавливаю NFQWS 2 Keenetic..."
soft_install_order "$dir" order || exit 1
echo "Установка NFQWS 2 Keenetic завершена."

if [ "$install_web" = "1" ]; then
    echo
    echo "Устанавливаю веб-интерфейс NFQWS..."
    soft_install_order "$dir" web-order || exit 1
    soft_reinstall_lighttpd "$dir" || exit 1
    echo "Установка веб-интерфейса NFQWS завершена."
    echo "Обычно доступен по адресу http://<IP_роутера>:90"
fi
exit 0
