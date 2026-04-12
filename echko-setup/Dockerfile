ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-requests py3-websocket-client curl

# Install cloudflared
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then CF_ARCH="amd64"; \
    elif [ "$ARCH" = "aarch64" ]; then CF_ARCH="arm64"; \
    elif [ "$ARCH" = "armv7l" ]; then CF_ARCH="arm"; \
    else CF_ARCH="amd64"; fi && \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

WORKDIR /app
COPY app.py .

COPY run.sh /etc/services.d/echko/run
RUN chmod +x /etc/services.d/echko/run
