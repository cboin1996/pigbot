FROM ubuntu:21.10
# Install necessary packages.
# Including rm -rf /var/lib/apt/lists/* saves memory by removing
# cached items related to the upgrade command
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && \
    apt-get -y upgrade && \
    apt-get install python3-pip -y && \
    rm -rf /var/lib/apt/lists/* 

WORKDIR /app
COPY app .
RUN pip install -r requirements.txt
# Run as non-root user:
RUN useradd --create-home appuser
USER appuser
ENTRYPOINT ["python3", "app.py"]