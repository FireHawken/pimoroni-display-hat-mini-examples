"""
displayhatmini_lite - Lightweight driver for Pimoroni Display HAT Mini

A NumPy-free replacement for the official displayhatmini library,
using luma.lcd for display communication.
"""

__version__ = "0.1.3"

import atexit
import os
import time

import RPi.GPIO as GPIO
from luma.core.interface.serial import spi
from luma.lcd.device import st7789
from PIL import Image


class KernelPWM:
    """Control PWM via kernel sysfs interface (more stable than pigpio)."""

    def __init__(self, chip=0, channel=0):
        self.chip = chip
        self.channel = channel
        self.base_path = f"/sys/class/pwm/pwmchip{chip}"
        self.pwm_path = f"{self.base_path}/pwm{channel}"
        self._exported = False
        self._period_ns = 0
        self._enabled = False

    def _export(self):
        """Export the PWM channel."""
        if not os.path.exists(self.pwm_path):
            try:
                with open(f"{self.base_path}/export", "w") as f:
                    f.write(str(self.channel))
                time.sleep(0.1)  # Wait for sysfs to create files
            except (IOError, OSError):
                return False
        self._exported = True
        return True

    def _write(self, filename, value):
        """Write value to sysfs file."""
        try:
            with open(f"{self.pwm_path}/{filename}", "w") as f:
                f.write(str(value))
            return True
        except (IOError, OSError):
            return False

    def set_frequency(self, freq_hz):
        """Set PWM frequency in Hz."""
        period_ns = int(1_000_000_000 / freq_hz)
        if self._enabled:
            self._write("enable", 0)
        self._write("period", period_ns)
        self._period_ns = period_ns

    def set_duty_cycle(self, duty_percent):
        """Set duty cycle as percentage (0-100)."""
        if self._period_ns > 0:
            duty_ns = int(self._period_ns * duty_percent / 100)
            self._write("duty_cycle", duty_ns)

    def enable(self):
        """Enable PWM output."""
        if self._write("enable", 1):
            self._enabled = True

    def disable(self):
        """Disable PWM output."""
        if self._write("enable", 0):
            self._enabled = False

    def cleanup(self):
        """Unexport the PWM channel."""
        if self._exported:
            try:
                self.disable()
                with open(f"{self.base_path}/unexport", "w") as f:
                    f.write(str(self.channel))
            except (IOError, OSError):
                pass

    @classmethod
    def is_available(cls, chip=0, channel=0):
        """Check if kernel PWM is available."""
        return os.path.exists(f"/sys/class/pwm/pwmchip{chip}")


class DisplayHATMini:
    """
    Driver for the Pimoroni Display HAT Mini.

    A 320x240 IPS display with RGB backlight LED and four buttons.
    """

    # Button GPIO pins (active low with pull-up)
    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24

    # RGB LED GPIO pins (active low - inverted logic)
    LED_R = 17
    LED_G = 27
    LED_B = 22

    # Display configuration
    SPI_PORT = 0
    SPI_CS = 1  # CE1
    SPI_DC = 9
    BACKLIGHT = 13

    # Display dimensions
    WIDTH = 320
    HEIGHT = 240

    # PWM frequencies
    LED_PWM_FREQ = 2000
    BACKLIGHT_PWM_FREQ = 2000  # 2 kHz - works well across all brightness levels

    # Kernel PWM configuration (GPIO 13 = PWM1 = channel 1)
    PWM_CHIP = 0
    PWM_CHANNEL = 1

    # SPI speed - 80 MHz works reliably and gives good performance
    SPI_SPEED_HZ = 80_000_000  # 80 MHz

    def __init__(self, backlight_pwm: bool = False, spi_speed_hz: int = None):
        """
        Initialize the Display HAT Mini.

        Args:
            backlight_pwm: If True, use PWM for dimmable backlight.
            spi_speed_hz: SPI bus speed in Hz. Default 80 MHz for best performance.
                         Can try 100_000_000 for ~20 FPS if display is stable.

        Note:
            For flicker-free backlight dimming, enable kernel PWM overlay:
                Add to /boot/firmware/config.txt:
                    dtoverlay=pwm-2chan,pin=13,func=4,pin2=18,func2=2
                Then reboot.

            For completely flicker-free operation, add a 0.1µF capacitor
            between GPIO 13 and GND.
        """
        self._backlight_pwm_enabled = backlight_pwm
        self._spi_speed = spi_speed_hz or self.SPI_SPEED_HZ
        self._button_callback = None
        self._kernel_pwm = None
        self._using_kernel_pwm = False

        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Set up buttons with pull-up resistors
        for pin in (self.BUTTON_A, self.BUTTON_B, self.BUTTON_X, self.BUTTON_Y):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Set up RGB LED with PWM
        self._led_pwm = {}
        for pin in (self.LED_R, self.LED_G, self.LED_B):
            GPIO.setup(pin, GPIO.OUT)
            pwm = GPIO.PWM(pin, self.LED_PWM_FREQ)
            pwm.start(100)  # Start at 100% duty = LED off (inverted)
            self._led_pwm[pin] = pwm

        # Set up backlight
        self._backlight_pwm = None
        if backlight_pwm:
            # Try kernel sysfs PWM first (most stable)
            if KernelPWM.is_available(self.PWM_CHIP, self.PWM_CHANNEL):
                try:
                    self._kernel_pwm = KernelPWM(self.PWM_CHIP, self.PWM_CHANNEL)
                    if self._kernel_pwm._export():
                        self._kernel_pwm.set_frequency(self.BACKLIGHT_PWM_FREQ)
                        self._kernel_pwm.set_duty_cycle(100)
                        self._kernel_pwm.enable()
                        self._using_kernel_pwm = True
                except Exception:
                    self._kernel_pwm = None

            # Fall back to software PWM if kernel PWM not available
            if not self._using_kernel_pwm:
                GPIO.setup(self.BACKLIGHT, GPIO.OUT)
                self._backlight_pwm = GPIO.PWM(self.BACKLIGHT, self.BACKLIGHT_PWM_FREQ)
                self._backlight_pwm.start(100)  # Full brightness
        else:
            GPIO.setup(self.BACKLIGHT, GPIO.OUT)
            GPIO.output(self.BACKLIGHT, GPIO.HIGH)

        # Initialize display via luma.lcd
        # Use 52 MHz initially (luma's max allowed), then override if higher requested
        initial_speed = min(self._spi_speed, 52_000_000)
        serial = spi(
            port=self.SPI_PORT,
            device=self.SPI_CS,
            gpio_DC=self.SPI_DC,
            gpio_RST=None,
            bus_speed_hz=initial_speed,
        )

        # Override SPI speed if higher than luma's whitelist allows
        if self._spi_speed > 52_000_000:
            serial._spi.max_speed_hz = self._spi_speed

        self._device = st7789(
            serial,
            width=self.WIDTH,
            height=self.HEIGHT,
            rotate=2,  # 180 degree rotation for correct orientation
        )

        # Register cleanup on exit
        atexit.register(self._cleanup)

    def set_led(self, r: float = 0.0, g: float = 0.0, b: float = 0.0) -> None:
        """
        Set the RGB LED color.

        Args:
            r: Red intensity (0.0 to 1.0)
            g: Green intensity (0.0 to 1.0)
            b: Blue intensity (0.0 to 1.0)

        Raises:
            ValueError: If any value is outside the 0.0-1.0 range.
        """
        for name, value in [("r", r), ("g", g), ("b", b)]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0 (got {value})")

        # Inverted logic: 100% duty = off, 0% duty = full brightness
        self._led_pwm[self.LED_R].ChangeDutyCycle((1.0 - r) * 100)
        self._led_pwm[self.LED_G].ChangeDutyCycle((1.0 - g) * 100)
        self._led_pwm[self.LED_B].ChangeDutyCycle((1.0 - b) * 100)

    def set_backlight(self, value: float) -> None:
        """
        Set the backlight brightness.

        Args:
            value: Brightness level (0.0 = off, 1.0 = full brightness)

        Raises:
            ValueError: If value is outside the 0.0-1.0 range.
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Backlight value must be between 0.0 and 1.0 (got {value})")

        if self._using_kernel_pwm and self._kernel_pwm:
            # Kernel sysfs PWM
            self._kernel_pwm.set_duty_cycle(value * 100)
        elif self._backlight_pwm:
            # Software PWM fallback
            self._backlight_pwm.ChangeDutyCycle(value * 100)
        else:
            # Simple on/off
            GPIO.output(self.BACKLIGHT, GPIO.HIGH if value > 0 else GPIO.LOW)

    def display(self, image: Image.Image) -> None:
        """
        Display a PIL Image on the screen.

        Args:
            image: A PIL Image object. Should be 320x240 RGB.
                  Will be converted/resized if necessary.

        Note:
            For best performance, pass images that are already 320x240 RGB
            to avoid conversion overhead.
        """
        self._device.display(image)

    def on_button_pressed(self, callback) -> None:
        """
        Register a callback for button events.

        The callback receives the GPIO pin number as its argument.
        Called on both press and release events.

        Args:
            callback: Function that takes one argument (pin number).
                     Use read_button(pin) inside to check state.
        """
        self._button_callback = callback

        for pin in (self.BUTTON_A, self.BUTTON_B, self.BUTTON_X, self.BUTTON_Y):
            # Remove any existing event detection
            try:
                GPIO.remove_event_detect(pin)
            except RuntimeError:
                pass

            # Add edge detection for both press and release
            GPIO.add_event_detect(
                pin,
                GPIO.BOTH,
                callback=self._handle_button,
                bouncetime=10
            )

    def _handle_button(self, pin: int) -> None:
        """Internal button event handler."""
        if self._button_callback:
            self._button_callback(pin)

    def read_button(self, pin: int) -> bool:
        """
        Read the current state of a button.

        Args:
            pin: The GPIO pin number (use BUTTON_A, BUTTON_B, etc.)

        Returns:
            True if the button is currently pressed, False otherwise.
        """
        # Buttons are active low (pressed = LOW)
        return not GPIO.input(pin)

    @property
    def using_hardware_pwm(self) -> bool:
        """Return True if using hardware PWM for backlight (kernel sysfs PWM)."""
        return self._using_kernel_pwm

    def _cleanup(self) -> None:
        """Clean up GPIO resources."""
        # Stop software PWM
        for pwm in self._led_pwm.values():
            pwm.stop()
        if self._backlight_pwm:
            self._backlight_pwm.stop()

        # Stop kernel PWM
        if self._kernel_pwm:
            self._kernel_pwm.cleanup()

        # Turn off LED and backlight
        for pin in (self.LED_R, self.LED_G, self.LED_B):
            GPIO.output(pin, GPIO.HIGH)  # LED off
        GPIO.setup(self.BACKLIGHT, GPIO.OUT)
        GPIO.output(self.BACKLIGHT, GPIO.LOW)  # Backlight off

    def __del__(self):
        """Destructor - clean up resources."""
        try:
            self._cleanup()
        except Exception:
            pass  # Ignore errors during cleanup
