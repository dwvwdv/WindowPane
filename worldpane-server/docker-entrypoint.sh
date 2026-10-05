#!/bin/sh
# Generate the pairing-code HMAC secret once and keep it in the volume, so `docker compose up`
# works with no configuration and pairing codes stay valid across restarts.
set -eu
if [ -z "${WORLDPANE_PAIRING_CODE_SECRET:-}" ]; then
    secret_file=/var/lib/worldpane/pairing_code_secret
    if [ ! -s "$secret_file" ]; then
        umask 077
        python -c "import secrets; print(secrets.token_urlsafe(32))" > "$secret_file"
    fi
    WORLDPANE_PAIRING_CODE_SECRET="$(cat "$secret_file")"
    export WORLDPANE_PAIRING_CODE_SECRET
fi
exec "$@"
