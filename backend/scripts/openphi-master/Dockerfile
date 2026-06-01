# Bare essentials Docker image for testing the OpenPhi API for Philips SDK.

# Directory where the Dockerfile is built has to include:
# - philips-pathologysdk-2.0-L1-ubuntu20_04_py38_research
# - testslide.isyntax
FROM ubuntu:20.04

# Author and Maintainer 
MAINTAINER Kimmo Kartasalo "kimmo.kartasalo@ki.se"

# Adding the user "docker" and switching to "docker" 
RUN useradd -ms /bin/bash docker
RUN su docker

# Avoid interactive prompts
ENV DEBIAN_FRONTEND noninteractive

#  Copy input files from the host to /app in the image
RUN mkdir app
WORKDIR app/
COPY . .

# See http://bugs.python.org/issue19846
ENV LANG C.UTF-8

# Install python, pip and any python packages
RUN apt-get update
RUN apt-get install -y python3.8 python3-pip
RUN python3 -m pip --no-cache-dir install --upgrade pip setuptools
RUN python3 -m pip install --no-cache-dir pillow==9.4 numpy==1.24

# Install Philips SDK (requires python 3.6.9)
RUN cd philips-pathologysdk-2.0-L1-ubuntu20_04_py38_research && ./InstallPathologySDK.sh -y
RUN cd ..

