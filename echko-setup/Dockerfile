ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip py3-requests

WORKDIR /app
COPY app.py .

CMD ["python3", "app.py"]
