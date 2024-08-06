FROM ubuntu:24.04
# Install necessary packages.
# Including rm -rf /var/lib/apt/lists/* saves memory by removing
# cached items related to the upgrade command
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get -y upgrade \
    && apt-get install -y python3-pip && apt-get install -y python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app .
RUN python3 -m venv venv
RUN ./venv/bin/pip install --upgrade pip && ./venv/bin/pip install -r requirements.txt
# Run as non-root user:
RUN useradd --create-home appuser
USER appuser
ENTRYPOINT ["./venv/bin/python3", "app/main.py"]
