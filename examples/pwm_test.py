#!/usr/bin/env python3
"""
pwm_test.py - Interactive PWM frequency and brightness tester

Controls:
- Button A: Increase brightness (+10%)
- Button B: Decrease brightness (-10%)
- Button X: Increase PWM frequency
- Button Y: Decrease PWM frequency

Uses pigpio for hardware PWM on GPIO 13 (backlight).
"""

import time
import pigpio
import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import st7789
from PIL import Image, ImageDraw, ImageFont

# GPIO pins
BACKLIGHT = 13
BUTTON_A = 5
BUTTON_B = 6
BUTTON_X = 16
BUTTON_Y = 24

# Available frequencies to test
FREQUENCIES = [100, 200, 500, 1000, 2000, 5000, 10000, 15000, 20000, 25000]

def main():
    # Initialize pigpio
    pi = pigpio.pi()
    if not pi.connected:
        print("Failed to connect to pigpio daemon!")
        print("Run: sudo systemctl start pigpiod")
        return

    # Initialize GPIO for buttons
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Initialize display
    serial = spi(port=0, device=1, gpio_DC=9, gpio_RST=None, bus_speed_hz=52000000)
    display = st7789(serial, width=320, height=240, rotate=2)

    # Load font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        font_small = font

    # Initial values
    brightness = 100  # percentage
    freq_index = 3    # 1000 Hz

    # State tracking for button debounce
    last_press = {BUTTON_A: 0, BUTTON_B: 0, BUTTON_X: 0, BUTTON_Y: 0}
    debounce_ms = 200

    def update_pwm():
        freq = FREQUENCIES[freq_index]
        duty = int(brightness / 100 * 1000000)
        pi.hardware_PWM(BACKLIGHT, freq, duty)

    def update_display():
        freq = FREQUENCIES[freq_index]
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)

        draw.text((20, 20), "PWM Backlight Tester", font=font, fill="black")

        draw.text((20, 70), f"Brightness: {brightness}%", font=font, fill="darkblue")
        draw.text((20, 100), f"Frequency: {freq} Hz", font=font, fill="darkred")

        # Draw brightness bar
        bar_x, bar_y = 20, 140
        bar_w, bar_h = 280, 20
        draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), outline="black")
        draw.rectangle((bar_x, bar_y, bar_x + int(bar_w * brightness / 100), bar_y + bar_h), fill="blue")

        draw.text((20, 175), "A/B: Brightness +/-", font=font_small, fill="gray")
        draw.text((20, 200), "X/Y: Frequency +/-", font=font_small, fill="gray")

        display.display(image)

    def read_button(pin):
        return not GPIO.input(pin)

    # Initial state
    update_pwm()
    update_display()

    print("PWM Backlight Tester")
    print("A/B: Brightness +/-")
    print("X/Y: Frequency +/-")
    print("Ctrl+C to exit")

    try:
        while True:
            now = time.time() * 1000
            changed = False

            # Button A - increase brightness
            if read_button(BUTTON_A) and now - last_press[BUTTON_A] > debounce_ms:
                last_press[BUTTON_A] = now
                brightness = min(100, brightness + 10)
                changed = True
                print(f"Brightness: {brightness}%")

            # Button B - decrease brightness
            if read_button(BUTTON_B) and now - last_press[BUTTON_B] > debounce_ms:
                last_press[BUTTON_B] = now
                brightness = max(0, brightness - 10)
                changed = True
                print(f"Brightness: {brightness}%")

            # Button X - increase frequency
            if read_button(BUTTON_X) and now - last_press[BUTTON_X] > debounce_ms:
                last_press[BUTTON_X] = now
                freq_index = min(len(FREQUENCIES) - 1, freq_index + 1)
                changed = True
                print(f"Frequency: {FREQUENCIES[freq_index]} Hz")

            # Button Y - decrease frequency
            if read_button(BUTTON_Y) and now - last_press[BUTTON_Y] > debounce_ms:
                last_press[BUTTON_Y] = now
                freq_index = max(0, freq_index - 1)
                changed = True
                print(f"Frequency: {FREQUENCIES[freq_index]} Hz")

            if changed:
                update_pwm()
                update_display()

            time.sleep(0.01)  # Small sleep to prevent CPU spinning

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        pi.hardware_PWM(BACKLIGHT, 0, 0)
        pi.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
