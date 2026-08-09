FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

ARG DEBIAN_FRONTEND=noninteractive
ARG RUSTUP_VERSION=1.29.0
ARG RUSTUP_SHA256=9732d6c5e2a098d3521fca8145d826ae0aaa067ef2385ead08e6feac88fa5792
ARG RUST_TOOLCHAIN=1.97.1
ARG GO_VERSION=1.26.5
ARG GO_SHA256=fe4789e92b1f33358680864bbe8704289e7bb5fc207d80623c308935bd696d49
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      autoconf automake autopoint bison build-essential ca-certificates cmake curl \
      debhelper devscripts dpkg-dev file flex gettext git gnupg gperf help2man \
      libtool lzip make meson ninja-build patch perl pkg-config python3 python3-tomli \
      rsync tar texinfo unzip xz-utils zip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLo /tmp/rustup-init \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/aarch64-unknown-linux-gnu/rustup-init" \
    && printf '%s  %s\n' "$RUSTUP_SHA256" /tmp/rustup-init | sha256sum -c - \
    && chmod +x /tmp/rustup-init \
    && /tmp/rustup-init -y --no-modify-path --profile minimal --default-toolchain "$RUST_TOOLCHAIN" \
    && /root/.cargo/bin/rustup target add wasm32-wasip1 --toolchain "$RUST_TOOLCHAIN" \
    && rm /tmp/rustup-init

RUN curl -fsSLo /tmp/go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-arm64.tar.gz" \
    && printf '%s  %s\n' "$GO_SHA256" /tmp/go.tar.gz | sha256sum -c - \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz

ENV PATH="/root/.cargo/bin:/usr/local/go/bin:${PATH}"
ENV RUSTUP_TOOLCHAIN="${RUST_TOOLCHAIN}"

WORKDIR /work
