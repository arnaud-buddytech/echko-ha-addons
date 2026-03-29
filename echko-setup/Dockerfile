ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-requests

WORKDIR /app
COPY app.py .

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
