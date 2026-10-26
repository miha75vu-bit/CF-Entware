#!/bin/sh
# Меню установщиков из /opt/Soft/Soft list.txt
list=/opt/Soft/Soft\ list.txt
[ -f "$list" ] || list="/opt/Soft/Soft-list.txt"

soft_pause() {
    printf '%s' "Нажмите Enter..."
    IFS= read -r _junk
}

soft_install_ipks() {
    _dir="$1"
    _n=0
    for _ipk in "$_dir"/*.ipk; do
        [ -f "$_ipk" ] || continue
        _n=1
        echo "Ставлю $(basename "$_ipk")..."
        if ! opkg install "$_ipk"; then
            echo "Не удалось поставить $_ipk"
            return 1
        fi
    done
    if [ "$_n" != "1" ]; then
        echo "В папке нет файлов .ipk: $_dir"
        return 1
    fi
    if [ -x /opt/usr/local/sbin/soft-index.sh ]; then
        /opt/usr/local/sbin/soft-index.sh || true
    fi
    return 0
}

while true; do
    clear 2>/dev/null || printf '\033c'
    echo "=== Установщики дополнительных программ ==="
    echo
    if [ ! -f "$list" ]; then
        echo "Нет файла списка: $list"
        echo
        echo "0) Выйти в командную строку"
        echo "99) Удалить папку с установщиками дополнительных программ"
        printf '%s' "Ваш выбор: "
        IFS= read -r ans
        ans=$(printf '%s' "$ans" | tr -d '\r')
        case "$ans" in
            0) exit 0 ;;
            99) sh /opt/usr/local/sbin/entware-remove-soft.sh; exit 0 ;;
            *) echo "Неверный выбор."; sleep 1 ;;
        esac
        continue
    fi

    while IFS= read -r line || [ -n "$line" ]; do
        line=$(printf '%s' "$line" | tr -d '\r')
        case "$line" in
            ''|'#'*) continue ;;
        esac
        _rest=$line
        _id=${_rest%% | *}
        _rest=${_rest#* | }
        _rest=${_rest#* | }
        _desc=${_rest#* | }
        echo "${_id}) ${_desc}"
    done < "$list"
    echo
    echo "0) Выйти в командную строку"
    echo "99) Удалить папку с установщиками дополнительных программ"
    echo
    printf '%s' "Ваш выбор: "
    IFS= read -r ans
    ans=$(printf '%s' "$ans" | tr -d '\r')
    [ -n "$ans" ] || continue
    case "$ans" in
        0) exit 0 ;;
        99)
            sh /opt/usr/local/sbin/entware-remove-soft.sh
            exit 0
            ;;
    esac

    _hit=""
    while IFS= read -r line || [ -n "$line" ]; do
        line=$(printf '%s' "$line" | tr -d '\r')
        case "$line" in
            ''|'#'*) continue ;;
        esac
        _rest=$line
        _id=${_rest%% | *}
        [ "$_id" = "$ans" ] || continue
        _rest=${_rest#* | }
        _type=${_rest%% | *}
        _rest=${_rest#* | }
        _folder=${_rest%% | *}
        _desc=${_rest#* | }
        _hit=1
        break
    done < "$list"

    if [ "$_hit" != "1" ]; then
        echo "Неверный выбор."
        sleep 1
        continue
    fi

    case "$_type" in
        info)
            echo
            echo "$_desc"
            echo
            soft_pause
            ;;
        script)
            _sh="/opt/Soft/${_folder}/install.sh"
            if [ ! -f "$_sh" ]; then
                echo "Нет установщика: $_sh"
                soft_pause
                continue
            fi
            echo
            sh "$_sh"
            echo
            echo "Возврат в меню."
            soft_pause
            ;;
        ipk)
            _dir="/opt/Soft/${_folder}"
            echo
            if soft_install_ipks "$_dir"; then
                if [ "$_folder" = "flashkeen" ] && [ -x /opt/bin/flashkeen ]; then
                    /opt/bin/flashkeen
                fi
            fi
            echo
            echo "Возврат в меню."
            soft_pause
            ;;
        *)
            echo "Неизвестный тип «$_type» в списке."
            soft_pause
            ;;
    esac
done
