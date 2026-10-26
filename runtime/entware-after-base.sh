#!/bin/sh
_profile=/opt/etc/profile
if [ -f "$_profile" ]; then
    if ! grep -q 'entware-login.sh' "$_profile" 2>/dev/null; then
        printf '\n%s\n%s\n' '# entware-login' '[ -r /opt/usr/local/sbin/entware-login.sh ] && . /opt/usr/local/sbin/entware-login.sh' >> "$_profile"
    fi
else
    printf '%s\n' '#!/bin/sh' 'export PATH="/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin"' '# entware-login' '[ -r /opt/usr/local/sbin/entware-login.sh ] && . /opt/usr/local/sbin/entware-login.sh' > "$_profile"
    chmod 644 "$_profile" 2>/dev/null || true
fi
exit 0
