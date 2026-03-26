FROM python:3.11-slim-bookworm AS pigpio-builder

ARG PIGPIO_VERSION=79

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

RUN curl -fsSL -o pigpio.tar.gz "https://github.com/joan2937/pigpio/archive/refs/tags/v${PIGPIO_VERSION}.tar.gz" \
    && tar -xzf pigpio.tar.gz \
    && make -C "pigpio-${PIGPIO_VERSION}" pigpiod

FROM python:3.11-slim-bookworm

ENV LD_LIBRARY_PATH=/usr/local/lib

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps espeak-ng espeak-ng-data \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=pigpio-builder /tmp/pigpio-79/pigpiod /usr/local/bin/pigpiod
COPY --from=pigpio-builder /tmp/pigpio-79/libpigpio.so.1 /usr/local/lib/libpigpio.so.1
RUN ln -s /usr/local/lib/libpigpio.so.1 /usr/local/lib/libpigpio.so

COPY . ./

# Pre-generate startup voice WAV
RUN mkdir -p /app/voice \
    && espeak-ng -v ru -s 130 -p 40 "Я ВЕРНУЛСЯ" -w /app/voice/startup.wav

CMD ["sh", "-c", "rm -f /var/run/pigpio.pid && pigpiod && sleep 1 && python -u main.py"]