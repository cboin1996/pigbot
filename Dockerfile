FROM ubuntu:24.04
# Install necessary packages.
# Including rm -rf /var/lib/apt/lists/* saves memory by removing
# cached items related to the upgrade command
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get -y upgrade \
    && apt-get install -y python3-pip python3-venv ffmpeg curl unzip && \
    # install deno for yt-dlp youtube extraction
    curl -fsSL https://deno.land/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app .
RUN python3 -m venv venv
RUN ./venv/bin/pip install --upgrade pip && ./venv/bin/pip install -r requirements.txt
# Run as non-root user:
RUN useradd --create-home appuser
RUN mkdir -p /home/appuser/.deno/bin && cp /root/.deno/bin/* /home/appuser/.deno/bin/
USER appuser
ENV PATH="/home/appuser/.deno/bin:$PATH"
RUN deno --help
ENTRYPOINT ["./venv/bin/python3", "main.py"]
