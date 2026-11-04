# Reproducible verification environment for AURA-HFT.
#   docker build -t aura-hft-ci .
#   docker run --rm -v "$PWD":/work aura-hft-ci make test
FROM ubuntu:24.04

ARG VERILATOR_VERSION=v5.040

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        make g++ python3 python3-venv python3-dev git ca-certificates \
        autoconf flex bison help2man perl libfl-dev zlib1g-dev ccache \
    && rm -rf /var/lib/apt/lists/*

# Verilator from source: cocotb 2.x needs >= 5.036, Ubuntu ships 5.020.
RUN git clone --depth 1 --branch ${VERILATOR_VERSION} https://github.com/verilator/verilator.git /tmp/verilator \
    && cd /tmp/verilator && autoconf && ./configure && make -j"$(nproc)" && make install \
    && rm -rf /tmp/verilator

COPY requirements.txt requirements-dev.txt /tmp/
RUN python3 -m venv $VIRTUAL_ENV \
    && pip install --no-cache-dir -r /tmp/requirements-dev.txt

WORKDIR /work
CMD ["make", "test"]
