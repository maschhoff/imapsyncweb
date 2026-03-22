# ── Stage 1: imapsync installer ──────────────────────────────────────────────
FROM debian:bookworm-slim AS imapsync-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    # imapsync Perl deps
    libauthen-ntlm-perl \
    libcgi-pm-perl \
    libcrypt-openssl-rsa-perl \
    libdata-uniqid-perl \
    libdigest-hmac-perl \
    libdist-checkconflicts-perl \
    libencode-imaputf7-perl \
    libfile-copy-recursive-perl \
    libfile-tail-perl \
    libio-socket-inet6-perl \
    libio-socket-ssl-perl \
    libio-tee-perl \
    libhtml-parser-perl \
    libjson-webtoken-perl \
    libmail-imapclient-perl \
    libmodule-scandeps-perl \
    libnet-dbus-perl \
    libnet-ssleay-perl \
    libpar-packer-perl \
    libreadonly-perl \
    libregexp-common-perl \
    libsys-meminfo-perl \
    libterm-readkey-perl \
    libtest-mockobject-perl \
    libtest-pod-perl \
    libunicode-string-perl \
    liburi-perl \
    libwww-perl \
    libtest-nowarnings-perl \
    libtest-deep-perl \
    libtest-warn-perl \
    make \
    && rm -rf /var/lib/apt/lists/*

# Download imapsync
RUN curl -fsSL https://raw.githubusercontent.com/imapsync/imapsync/master/imapsync \
    -o /usr/local/bin/imapsync \
    && chmod +x /usr/local/bin/imapsync

# ── Stage 2: final image ──────────────────────────────────────────────────────
FROM debian:bookworm-slim

LABEL maintainer="imapsync-web" \
      description="imapsync web UI — IMAP migration tool with a modern web interface" \
      org.opencontainers.image.source="https://github.com/imapsync/imapsync"

# Install runtime dependencies: Perl libs for imapsync + Python for Flask
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Perl runtime deps (same as builder, minus build tools)
    libauthen-ntlm-perl \
    libcgi-pm-perl \
    libcrypt-openssl-rsa-perl \
    libdata-uniqid-perl \
    libdigest-hmac-perl \
    libdist-checkconflicts-perl \
    libencode-imaputf7-perl \
    libfile-copy-recursive-perl \
    libfile-tail-perl \
    libio-socket-inet6-perl \
    libio-socket-ssl-perl \
    libio-tee-perl \
    libhtml-parser-perl \
    libjson-webtoken-perl \
    libmail-imapclient-perl \
    libmodule-scandeps-perl \
    libnet-dbus-perl \
    libnet-ssleay-perl \
    libpar-packer-perl \
    libreadonly-perl \
    libregexp-common-perl \
    libsys-meminfo-perl \
    libterm-readkey-perl \
    libtest-mockobject-perl \
    libtest-pod-perl \
    libunicode-string-perl \
    liburi-perl \
    libwww-perl \
    libtest-nowarnings-perl \
    libtest-deep-perl \
    libtest-warn-perl \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    # Misc
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy imapsync binary from builder stage
COPY --from=imapsync-builder /usr/local/bin/imapsync /usr/local/bin/imapsync

# Create app user (don't run as root)
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app

# Install Python dependencies in a venv
COPY requirements.txt .
RUN python3 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /app/.venv/bin/pip install --no-cache-dir gunicorn

# Copy application files
COPY app.py .
COPY templates/ templates/

# Ensure correct ownership
RUN chown -R appuser:appuser /app

USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/check')" || exit 1

# Use gunicorn for production; fall back to flask dev server via env var
CMD gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --timeout 300 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    app:app
