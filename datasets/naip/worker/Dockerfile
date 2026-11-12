# Stock GDAL plus boto3 and the converter. Built for linux/arm64 (Fargate on Graviton).
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-boto3 \
    && rm -rf /var/lib/apt/lists/*

COPY convert.py mosaic.py /opt/naip/

ENTRYPOINT ["python3", "/opt/naip/convert.py"]
