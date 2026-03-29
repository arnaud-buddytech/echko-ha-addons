#!/usr/bin/with-contenv bashio
set -e
bashio::log.info "Starting Echko Setup on port 7080..."
exec python3 /app/app.py
