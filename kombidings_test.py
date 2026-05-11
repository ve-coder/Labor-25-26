#!/usr/bin/env python3
"""
Test-Version: Nur Kamera + Farberkennung (OHNE Motors/GPIO)
Ideal um die Kamera zu testen ohne dass die Hardware verkabelt sein muss.
"""

import cv2
import time
import sys

try:
    from picamera2 import Picamera2
except Exception as e:
    print(f"FEHLER: picamera2 nicht verfügbar: {e}")
    Picamera2 = None

from cube_config import CALIB_ORDER, CV_WINDOW
from cube_vision import (
    calibrate_face_avg9,
    draw_grid,
    draw_live_labels,
    load_calib,
    put_info,
    save_calib,
    scan_face_3x3,
)


def test_camera():
    """
    Test-Modus: Nur Kamera-Feed + Farberkennung.
    Keine Motoren, keine GPIO.
    """
    
    if Picamera2 is None:
        print("ERROR: picamera2 nicht verfügbar!")
        print("Bist du auf einem Raspberry Pi? Sonst: pip install picamera2")
        sys.exit(1)
    
    print("=" * 60)
    print("RUBIKS CUBE - KAMERA TEST (Keine Hardware nötig)")
    print("=" * 60)
    print()
    print("BEDIENUNG:")
    print("  SPACE      = Foto für Kalibrierung")
    print("  ESC        = Beenden")
    print()
    
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"format": "BGR888", "size": (1280, 720)}
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.5)
    
    cv2.namedWindow(CV_WINDOW, cv2.WINDOW_AUTOSIZE)
    
    calib = {}
    
    try:
        # Lade existierende Kalibrierung
        loaded_calib = load_calib()
        if loaded_calib:
            calib = loaded_calib
            print(f"✓ Kalibrierung geladen: {len(calib)} Flächen")
        else:
            print("Keine Kalibrierung gefunden. Neue wird erstellt.")
    except Exception as e:
        print(f"Warnung: Kalibrierung nicht ladbar: {e}")
    
    print()
    print("Starte Kamera-Feed...")
    print()
    
    try:
        while True:
            frame_bgr = picam2.capture_array()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            
            # Grid zeichnen (3x3)
            draw_grid(frame_bgr)
            
            # Live-Farberkennung (wenn kalibriert)
            if len(calib) >= 1:
                live = scan_face_3x3(frame_rgb, calib)
                draw_live_labels(frame_bgr, live)
            
            # Info anzeigen
            info_text = [
                "TEST MODE: Nur Kamera (keine Hardware)",
                f"Kalibriert: {len(calib)}/6 Flächen",
            ]
            
            if len(calib) < 6:
                info_text.append("SPACE = Nächste Fläche kalibrieren")
            else:
                info_text.append("Farberkennung aktiv!")
            
            info_text.append("ESC = Beenden")
            
            put_info(frame_bgr, info_text)
            
            cv2.imshow(CV_WINDOW, frame_bgr)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:  # ESC
                print("\n✓ Beendet.")
                break
            
            if key == 32:  # SPACE
                if len(calib) < 6:
                    face_idx = len(calib)
                    face_letter, face_name = CALIB_ORDER[face_idx]
                    
                    print(f"\nKalibriere Fläche {face_idx + 1}/6: {face_name} ({face_letter})")
                    print("Halte diese Fläche ins Licht und drücke SPACE...")
                    
                    # Warte auf nächsten SPACE
                    while True:
                        frame_bgr = picam2.capture_array()
                        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                        
                        draw_grid(frame_bgr)
                        put_info(
                            frame_bgr,
                            [
                                f"KALIBRIERUNG {face_idx + 1}/6: {face_name}",
                                "Halte diese Fläche ins Licht.",
                                "SPACE = OK   ESC = Abbrechen",
                            ],
                        )
                        
                        cv2.imshow(CV_WINDOW, frame_bgr)
                        k = cv2.waitKey(1) & 0xFF
                        
                        if k == 27:
                            print("Kalibrierung abgebrochen.")
                            break
                        
                        if k == 32:
                            try:
                                calib_data = calibrate_face_avg9(frame_rgb)
                                if calib_data:
                                    calib[face_letter] = calib_data
                                    print(f"✓ {face_name} kalibriert!")
                                    
                                    if len(calib) == 6:
                                        save_calib(calib)
                                        print("✓ ALLE 6 FLÄCHEN KALIBRIERT UND GESPEICHERT!")
                                else:
                                    print(f"✗ Kalibrierung fehlgeschlagen für {face_name}")
                            except Exception as e:
                                print(f"✗ Fehler: {e}")
                            break
    
    except KeyboardInterrupt:
        print("\n✓ Durch Ctrl+C beendet.")
    
    except Exception as e:
        print(f"\n✗ FEHLER: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            picam2.stop()
        except:
            pass
        
        try:
            cv2.destroyAllWindows()
        except:
            pass
        
        print("\n" + "=" * 60)
        print(f"Final: {len(calib)}/6 Flächen kalibriert")
        print("=" * 60)


if __name__ == "__main__":
    test_camera()
