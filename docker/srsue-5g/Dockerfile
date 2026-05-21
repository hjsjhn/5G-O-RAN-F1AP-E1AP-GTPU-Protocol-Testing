FROM ubuntu:jammy AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      cmake \
      git \
      libboost-program-options-dev \
      libboost-system-dev \
      libboost-test-dev \
      libboost-thread-dev \
      libconfig++-dev \
      libfftw3-dev \
      libmbedtls-dev \
      libsctp-dev \
      libzmq3-dev \
      pkg-config && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/srsran/srsRAN_4G.git /src/srsRAN_4G && \
    cd /src/srsRAN_4G && \
    git checkout ec29b0c1ff79cebcbe66caa6d6b90778261c42b8 && \
    sed -i 's/#define FFTW_TYPE FFTW_MEASURE/#define FFTW_TYPE FFTW_ESTIMATE/' lib/src/phy/dft/dft_fftw.c && \
    mkdir build && \
    cd build && \
    cmake -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF -DENABLE_SOAPYSDR=OFF ../ && \
    make -j"$(nproc)" srsue && \
    make install && \
    ldconfig

FROM ubuntu:jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      iproute2 \
      libboost-program-options1.74.0 \
      libboost-system1.74.0 \
      libboost-thread1.74.0 \
      libconfig++9v5 \
      libfftw3-single3 \
      libmbedtls14 \
      libsctp1 \
      libzmq5 \
      net-tools && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/bin/srsue /usr/local/bin/srsue
COPY --from=builder /usr/local/lib/ /usr/local/lib/

RUN ldconfig && mkdir -p /etc/srsran

CMD ["/usr/local/bin/srsue", "/etc/srsran/ue.conf"]
