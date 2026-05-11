# Rubiks Cube - Kamera Test ohne Hardware

## Was du brauchst:
- ✅ Raspberry Pi mit Docker installiert
- ✅ Picamera2 (USB-Kamera funktioniert auch)
- ✅ Dieses Git-Repo geclont
- ❌ KEINE Motors, Relays, GPIO verkabelt nötig!

## Quick Start

### 1. Auf dem Raspberry Pi:

```bash
cd ~/Labor-25-26
git pull origin main
```

### 2. Build des Test-Images:

```bash
docker build -f Dockerfile.test -t rubiks-test .
```

Oder mit Compose:
```bash
docker compose -f docker-compose.test.yml build
```

### 3. Starten:

```bash
docker compose -f docker-compose.test.yml up
```

Logs anschauen:
```bash
docker compose -f docker-compose.test.yml logs -f
```

### 4. Beende den Test:

```bash
docker compose -f docker-compose.test.yml down
```

---

## Was wird getestet?

- ✅ Kamera-Zugriff (/dev/video0)
- ✅ Picamera2 funktioniert
- ✅ OpenCV lädt Bilder
- ✅ Farb-Kalibrierung (6 Seiten)
- ✅ Live-Farberkennung

---

## Bedienung in der Test-App

```
SPACE   = Nächste Fläche kalibrieren
ESC     = Beenden
```

### Kalibrierungs-Workflow:

1. App startet → zeigt Kamera-Feed
2. Du drückst SPACE → App wartet auf Fläche 1 (weiß)
3. Du hältst die weiße Seite ins Licht
4. Du drückst SPACE → kalibriert die Farben dieser Seite
5. Wiederhole für alle 6 Seiten
6. Am Ende: Farberkennung aktiv!

---

## Fehler beheben

### "picamera2 not available"
- Nur auf Raspberry Pi mit Camera Module, nicht auf Desktop-Linux
- Verwende USB-Kamera als Fallback

### "Cannot access /dev/video0"
- Kamera nicht angeschlossen?
- Docker-Gruppe Berechtigungen: `sudo usermod -aG video $USER`

### Build-Fehler
```bash
# Cache clearen
docker system prune -a

# Neu bauen
docker build -f Dockerfile.test -t rubiks-test .
```

---

## Nächste Schritte (später mit Hardware)

1. Wenn Hardware verkabelt: `docker-compose.yml` verwenden
2. `Dockerfile` statt `Dockerfile.test`
3. Mit `kombidings_app.py` statt `kombidings_test.py`
