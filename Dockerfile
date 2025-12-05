# LogSynth Docker Image
# Multi-stage build for minimal image size

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy source files
COPY pyproject.toml README.md ./
COPY logsynth/ logsynth/

# Build wheel
RUN python -m build --wheel


FROM python:3.12-slim

LABEL maintainer="lance0"
LABEL description="LogSynth - Flexible synthetic log generator"
LABEL version="0.2.0"

WORKDIR /app

# Copy wheel from builder
COPY --from=builder /build/dist/*.whl /tmp/

# Install logsynth
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Create config directory
RUN mkdir -p /root/.config/logsynth/profiles /root/.config/logsynth/plugins

# Copy presets for reference (already installed via package)
# Users can mount custom templates at /templates

VOLUME ["/templates", "/output", "/root/.config/logsynth"]

# Default to help if no arguments
ENTRYPOINT ["logsynth"]
CMD ["--help"]
