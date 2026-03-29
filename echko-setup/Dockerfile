ARG BUILD_FROM
FROM $BUILD_FROM

RUN pip3 install --no-cache-dir requests

WORKDIR /app
COPY app.py .

CMD ["python3", "app.py"]
