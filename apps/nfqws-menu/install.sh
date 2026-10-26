#!/bin/sh
dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 1
src="$dir/nfqws-menu.sh"
dst=/opt/nfqws-menu.sh
if [ ! -f "$src" ]; then
    echo "В архиве нет nfqws-menu.sh."
    exit 1
fi
echo "Устанавливаю nfqws-menu..."
cp -f "$src" "$dst" || exit 1
chmod +x "$dst" || exit 1
echo "Дальше откроется меню nfqws-menu. После выхода вернётесь к списку установщиков."
echo
sh "$dst"
exit 0
