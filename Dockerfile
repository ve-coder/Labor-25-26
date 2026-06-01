FROM arm64v8/python:3.11-slim-bookworm

# Raspberry Pi apt-Repository hinzufügen (für python3-libcamera und python3-kms++)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg \
    && curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
       | gpg --dearmor -o /etc/apt/trusted.gpg.d/raspberrypi.gpg \
    && echo "deb http://archive.raspberrypi.com/debian/ bookworm main" \
       > /etc/apt/sources.list.d/raspi.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        
        libatlas-base-dev \
        libharfbuzz0b \
        libwebp7 \
        libtiff6 \
        libopenjp2-7 \
        gcc \
        python3-libcamera \
        python3-kms++ \
        libgl1 \
        libgles2 \
        libegl1 \
        libx11-6 \
        libxrandr2 \
    && rm -rf /var/lib/apt/lists/*

# System-Python-Pakete (libcamera, kmsxx) für den pip-Python zugänglich machen,
# aber NACH pip-Paketen damit pip-Versionen Vorrang haben
RUN echo "/usr/lib/python3/dist-packages" \
    >> /usr/local/lib/python3.11/site-packages/raspi-packages.pth

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "kombidings_app.py"]
