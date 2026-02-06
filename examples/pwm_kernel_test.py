#!/usr/bin/env python3
"""
pwm_kernel_test.py - Test backlight using kernel sysfs PWM (no pigpio)

Controls:
- Button A: Increase brightness (+10%)
- Button B: Decrease brightness (-10%)
- Button X: Increase PWM frequency
- Button Y: Decrease PWM frequency

Uses kernel sysfs PWM on GPIO 13 - should be more stable than pigpio.
Requires: dtoverlay=pwm-2chan,pin=13,func=4 in /boot/firmware/config.txt
"""

import os
import time
import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import st7789
from PIL import Image, ImageDraw, ImageFont

# GPIO pins
BUTTON_A = 5
BUTTON_B = 6
BUTTON_X = 16
BUTTON_Y = 24

# PWM chip and channel (GPIO 13 = PWM1 = channel 1)
PWM_CHIP = 0
PWM_CHANNEL = 1

# Available frequencies to test (in Hz)
FREQUENCIES = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]


class KernelPWM:
    """Control PWM via kernel sysfs interface."""

    def __init__(self, chip=0, channel=0):
        self.chip = chip
        self.channel = channel
        self.base_path = f"/sys/class/pwm/pwmchip{chip}"
        self.pwm_path = f"{self.base_path}/pwm{channel}"
        self._exported = False
        self._export()

    def _export(self):
        """Export the PWM channel."""
        if not os.path.exists(self.pwm_path):
            with open(f"{self.base_path}/export", "w") as f:
                f.write(str(self.channel))
            time.sleep(0.1)  # Wait for sysfs to create files
        self._exported = True

    def _write(self, filename, value):
        """Write value to sysfs file."""
        with open(f"{self.pwm_path}/{filename}", "w") as f:
            f.write(str(value))

    def _read(self, filename):
        """Read value from sysfs file."""
        with open(f"{self.pwm_path}/{filename}", "r") as f:
            return f.read().strip()

    def set_frequency(self, freq_hz):
        """Set PWM frequency in Hz."""
        period_ns = int(1_000_000_000 / freq_hz)
        # Must disable before changing period
        try:
            self._write("enable", 0)
        except:
            pass
        self._write("period", period_ns)
        self._period_ns = period_ns

    def set_duty_cycle(self, duty_percent):
        """Set duty cycle as percentage (0-100)."""
        duty_ns = int(self._period_ns * duty_percent / 100)
        self._write("duty_cycle", duty_ns)

    def enable(self):
        """Enable PWM output."""
        self._write("enable", 1)

    def disable(self):
        """Disable PWM output."""
        self._write("enable", 0)

    def cleanup(self):
        """Unexport the PWM channel."""
        if self._exported:
            try:
                self.disable()
                with open(f"{self.base_path}/unexport", "w") as f:
                    f.write(str(self.channel))
            except:
                pass


def main():
    # Initialize kernel PWM
    try:
        pwm = KernelPWM(chip=PWM_CHIP, channel=PWM_CHANNEL)
    except Exception as e:
        print(f"Failed to initialize kernel PWM: {e}")
        print("Make sure dtoverlay=pwm-2chan is in /boot/firmware/config.txt")
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
    brightness = 100
    freq_index = 3  # 1000 Hz

    # State tracking for button debounce
    last_press = {BUTTON_A: 0, BUTTON_B: 0, BUTTON_X: 0, BUTTON_Y: 0}
    debounce_ms = 200

    def update_pwm():
        freq = FREQUENCIES[freq_index]
        pwm.set_frequency(freq)
        pwm.set_duty_cycle(brightness)
        pwm.enable()

    def update_display():
        freq = FREQUENCIES[freq_index]
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)

        draw.text((20, 15), "Kernel PWM Test", font=font, fill="black")

        draw.text((20, 60), f"Brightness: {brightness}%", font=font, fill="darkblue")
        draw.text((20, 90), f"Frequency: {freq} Hz", font=font, fill="darkred")

        # Draw brightness bar
        bar_x, bar_y = 20, 130
        bar_w, bar_h = 280, 20
        draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), outline="black")
        draw.rectangle((bar_x, bar_y, bar_x + int(bar_w * brightness / 100), bar_y + bar_h), fill="blue")

        draw.text((20, 165), "A/B: Brightness +/-", font=font_small, fill="gray")
        draw.text((20, 190), "X/Y: Frequency +/-", font=font_small, fill="gray")
        draw.text((20, 215), "(Kernel sysfs PWM)", font=font_small, fill="darkgreen")

        display.display(image)

    def read_button(pin):
        return not GPIO.input(pin)

    # Initial state
    update_pwm()
    update_display()

    print("Kernel PWM Backlight Tester")
    print(f"Frequencies available: {FREQUENCIES}")
    print("A/B: Brightness +/-")
    print("X/Y: Frequency +/-")
    print("Ctrl+C to exit")

    try:
        while True:
            now = time.time() * 1000
            changed = False

            if read_button(BUTTON_A) and now - last_press[BUTTON_A] > debounce_ms:
                last_press[BUTTON_A] = now
                brightness = min(100, brightness + 10)
                changed = True
                print(f"Brightness: {brightness}%")

            if read_button(BUTTON_B) and now - last_press[BUTTON_B] > debounce_ms:
                last_press[BUTTON_B] = now
                brightness = max(0, brightness - 10)
                changed = True
                print(f"Brightness: {brightness}%")

            if read_button(BUTTON_X) and now - last_press[BUTTON_X] > debounce_ms:
                last_press[BUTTON_X] = now
                freq_index = min(len(FREQUENCIES) - 1, freq_index + 1)
                changed = True
                print(f"Frequency: {FREQUENCIES[freq_index]} Hz")

            if read_button(BUTTON_Y) and now - last_press[BUTTON_Y] > debounce_ms:
                last_press[BUTTON_Y] = now
                freq_index = max(0, freq_index - 1)
                changed = True
                print(f"Frequency: {FREQUENCIES[freq_index]} Hz")

            if changed:
                update_pwm()
                update_display()

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        pwm.cleanup()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
