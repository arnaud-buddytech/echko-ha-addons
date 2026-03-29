ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip && pip3 install --no-cache-dir --break-system-packages requests

WORKDIR /app
COPY app.py .

CMD ["python3", "app.py"]
