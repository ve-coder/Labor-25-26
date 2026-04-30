# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM arm64v8/python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM arm64v8/python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV runtime dependencies
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    # X11 / display support (cv2.imshow + Ursina / OpenGL)
    libx11-6 \
    libxrandr2 \
    libxfixes3 \
    libxi6 \
    libxcursor1 \
    libxinerama1 \
    libgles2 \
    # libcamera / picamera2 C libraries
    libcamera0 \
    libcamera-ipa \
    v4l-utils \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    # Image-format libraries used by OpenCV
    libjpeg62-turbo \
    libtiff6 \
    libopenjp2-7 \
    libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages installed in the build stage
COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

# Copy application source
COPY . .

CMD ["python", "kombidings_app.py"]
