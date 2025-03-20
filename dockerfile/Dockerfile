## ADPATED FROM ORIGINAL detectron2/docker/Dockerfile

FROM pytorch/pytorch:2.5.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
    python3-dev \
    python3-pip \
    python3-opencv \
    git \
    gcc \
    wget \
    ninja-build \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
    apt-get install -y sudo && \
    apt-get clean


RUN python3 -m pip install --upgrade pip
COPY . .

RUN dpkg -i quarto-1.5.57-linux-amd64.deb 
RUN apt-get install -f

RUN pip install -r requirements.txt
RUN pip install 'git+https://github.com/facebookresearch/detectron2.git'


RUN ln -s /usr/bin/python3 /usr/bin/python
RUN adduser bbg
RUN usermod -aG sudo bbg

RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
USER bbg

