ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-requests

WORKDIR /app
COPY app.py .

COPY run.sh /etc/services.d/echko/run
RUN chmod +x /etc/services.d/echko/run
