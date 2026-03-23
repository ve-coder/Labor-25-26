import RPi.GPIO as GPIO
import time
import sys
import tty
import termios

# Pins
STEP = 17
DIR = 27
EN = 23

# Motor configuration
STEPS_PER_REVOLUTION = 200  # Change this based on your motor (200 for 1.8°, 400 for 0.9°)
MICROSTEPS = 1  # Change this if you're using microstepping (1, 2, 4, 8, 16)
STEPS_FOR_90_DEGREES = (STEPS_PER_REVOLUTION * MICROSTEPS) // 4

# Speed configuration - LANGSAMER!
STEP_DELAY = 0.005  # 5ms zwischen jedem Schritt = langsame, sanfte Bewegung

# Setup GPIO
GPIO.setmode(GPIO. BCM)
GPIO.setup([STEP, DIR, EN], GPIO.OUT)

# Motor ist am Anfang AUS
GPIO.output(EN, GPIO.HIGH)  # HIGH = Motor deaktiviert
GPIO.output(STEP, GPIO.LOW)
GPIO.output(DIR, GPIO. LOW)

def get_key():
    """Read a single keypress without requiring Enter"""
    fd = sys. stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def enable_motor():
    """Motor einschalten"""
    GPIO.output(EN, GPIO.LOW)
    time.sleep(0.01)  # Kurze Pause damit Motor bereit ist

def disable_motor():
    """Motor ausschalten - WICHTIG für Stromlosigkeit"""
    GPIO.output(EN, GPIO.HIGH)
    GPIO.output(STEP, GPIO. LOW)
    GPIO.output(DIR, GPIO.LOW)
    time.sleep(0.01)

def rotate_motor(steps, direction):
    """
    Rotate the motor a specific number of steps

    Args:
        steps: Number of steps to rotate
        direction: GPIO. HIGH for one direction, GPIO.LOW for the other
    """
    enable_motor()  # Motor einschalten

    GPIO.output(DIR, direction)
    time.sleep(0.01)  # Richtung setzen

    print(f"Bewege Motor mit {steps} Schritten (Verzögerung: {STEP_DELAY*1000:.1f}ms pro Schritt)...")

    for i in range(steps):
        GPIO.output(STEP, GPIO. HIGH)
        time.sleep(STEP_DELAY)
        GPIO.output(STEP, GPIO.LOW)
        time.sleep(STEP_DELAY)

        # Fortschrittsanzeige alle 10 Schritte
        if (i + 1) % 10 == 0 or (i + 1) == steps:
            progress = ((i + 1) / steps) * 100
            print(f"  Fortschritt: {progress:.0f}% ({i+1}/{steps} Schritte)", end='\r')

    print()  # Neue Zeile nach Fortschrittsanzeige
    disable_motor()  # Motor wieder ausschalten!

def main():
    print("=" * 50)
    print("Stepper Motor Control - LANGSAM & SICHER")
    print("=" * 50)
    print(f"Steps per revolution: {STEPS_PER_REVOLUTION}")
    print(f"Microsteps: {MICROSTEPS}")
    print(f"Steps for 90°: {STEPS_FOR_90_DEGREES}")
    print(f"Verzögerung pro Schritt: {STEP_DELAY*1000:.1f}ms")
    print(f"Zeit für 90°: ca. {(STEPS_FOR_90_DEGREES * STEP_DELAY * 2):.1f} Sekunden")
    print("=" * 50)
    print("\nControls:")
    print("  'r' - Rotate 90° clockwise (rechts)")
    print("  'l' - Rotate 90° counter-clockwise (links)")
    print("  'o' - Motor AUSschalten (OFF)")
    print("  'q' - Programm beenden")
    print("\n⚠️  Motor ist AUSGESCHALTET.  Drücke 'r' oder 'l' zum Bewegen.\n")

    try:
        while True:
            key = get_key().lower()

            if key == 'r':
                print("\n→ Drehe 90° im Uhrzeigersinn (rechts)...")
                rotate_motor(STEPS_FOR_90_DEGREES, GPIO.HIGH)
                print("✓ Fertig!  Motor ist wieder AUS.\n")

            elif key == 'l':
                print("\n← Drehe 90° gegen Uhrzeigersinn (links)...")
                rotate_motor(STEPS_FOR_90_DEGREES, GPIO.LOW)
                print("✓ Fertig!  Motor ist wieder AUS.\n")

            elif key == 'o':
                print("\n⏸  Motor AUSGESCHALTET")
                disable_motor()
                print("✓ Motor ist stromlos.\n")

            elif key == 'q':
                print("\n\nBeende Programm...")
                break

            else:
                print(f"\n❌ Unbekannte Taste: '{key}'.  Nutze 'r', 'l', 'o' oder 'q'\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Programm durch Benutzer unterbrochen.")

    finally:
        print("\n🔧 Räume GPIO auf und schalte Motor AUS...")
        disable_motor()
        time.sleep(0.1)
        GPIO.cleanup()
        print("✓ GPIO bereinigt. Motor ist AUS.  Auf Wiedersehen!\n")

if __name__ == "__main__":
    main()