# displayhatmini-lite

A lightweight, NumPy-free Python driver for the **Pimoroni Display HAT Mini** — works out-of-the-box on Raspberry Pi Zero 2 W and other resource-constrained devices.

## Why This Exists

The official [displayhatmini-python](https://github.com/pimoroni/displayhatmini-python) library depends on NumPy, which:

- Has no prebuilt wheels for Python 3.13 on ARM
- Falls back to source compilation that takes hours on Pi Zero
- Often fails entirely due to memory constraints

This library provides a **drop-in replacement** using [luma.lcd](https://github.com/rm-hull/luma.lcd) — a mature, lightweight display driver that works cleanly without NumPy.

## Features

- **ST7789 display** (320×240) via `luma.lcd`
- **RGB LED** control with PWM brightness
- **Backlight** control (on/off or PWM dimming)
- **Four buttons** with callback support
- **API-compatible** with the original `displayhatmini` library
- **Python 3.9+** including 3.13

## Hardware

| Function     | GPIO (BCM) |
|--------------|------------|
| SPI MOSI     | 10         |
| SPI SCLK     | 11         |
| SPI CE1 (CS) | 7          |
| DC           | 9          |
| Backlight    | 13         |
| LED Red      | 17         |
| LED Green    | 27         |
| LED Blue     | 22         |
| Button A     | 5          |
| Button B     | 6          |
| Button X     | 16         |
| Button Y     | 24         |

## Installation

### Prerequisites

Enable SPI on your Raspberry Pi:

```bash
sudo raspi-config nonint do_spi 0
```

Or add to `/boot/firmware/config.txt`:

```ini
dtparam=spi=on
```

#### Optional: Flicker-Free Backlight Dimming

For smooth, flicker-free backlight dimming, enable kernel PWM by adding this line to `/boot/firmware/config.txt`:

```ini
dtoverlay=pwm-2chan,pin=13,func=4,pin2=18,func2=2
```

Then reboot. The library will automatically use kernel PWM when available, falling back to software PWM otherwise.

**Hardware fix for completely flicker-free operation:** Add a 0.1µF ceramic capacitor between GPIO 13 and GND. This eliminates all brightness spikes and dips, especially noticeable at mid-range brightness levels.

### System Dependencies

```bash
sudo apt update
sudo apt install -y \
  python3-pil \
  python3-spidev \
  python3-rpi.gpio \
  fonts-dejavu-core \
  libfreetype6 \
  libjpeg62-turbo \
  zlib1g
```

**Important:** Install fonts and freetype *before* creating your virtual environment, otherwise TrueType fonts won't work in Pillow.

### Install the Package

```bash
pip install displayhatmini-lite
```

Or for development:

```bash
git clone https://github.com/FireHawken/pimoroni-display-hat-mini-examples.git
cd pimoroni-display-hat-mini-examples
pip install -e .
```

### Virtual Environment Notes

GPIO access requires system packages. Create your venv with:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

## Quick Start

```python
from displayhatmini_lite import DisplayHATMini
from PIL import Image, ImageDraw, ImageFont

# Create display instance
display = DisplayHATMini()

# Turn on backlight
display.set_backlight(1.0)

# Set RGB LED to purple
display.set_led(1.0, 0.0, 1.0)

# Draw something
image = Image.new("RGB", (320, 240), "black")
draw = ImageDraw.Draw(image)
draw.text((10, 100), "Hello World!", fill="white")

# Send to display
display.display(image)

# Button handling
def button_callback(pin):
    if not display.read_button(pin):  # Button released
        return
    if pin == DisplayHATMini.BUTTON_A:
        print("Button A pressed!")

display.on_button_pressed(button_callback)
```

## API Reference

### DisplayHATMini

#### Constants

```python
# Buttons
DisplayHATMini.BUTTON_A  # GPIO 5
DisplayHATMini.BUTTON_B  # GPIO 6
DisplayHATMini.BUTTON_X  # GPIO 16
DisplayHATMini.BUTTON_Y  # GPIO 24

# Display dimensions
DisplayHATMini.WIDTH   # 320
DisplayHATMini.HEIGHT  # 240
```

#### Methods

| Method | Description |
|--------|-------------|
| `__init__(backlight_pwm=False, spi_speed_hz=None)` | Initialize display. Set `backlight_pwm=True` for dimmable backlight. Default SPI speed is 80 MHz. |
| `set_led(r, g, b)` | Set RGB LED color (0.0–1.0 per channel) |
| `set_backlight(value)` | Set backlight brightness (0.0–1.0) |
| `display(image)` | Send PIL Image to the display |
| `on_button_pressed(callback)` | Register button event callback |
| `read_button(pin)` | Read button state (True = pressed) |
| `using_hardware_pwm` | Property: True if using kernel PWM for backlight |

## Examples

See the `examples/` directory:

- `hello.py` — Basic display and LED test
- `pong.py` — Classic Pong game using the buttons
- `backlight_pwm.py` — Backlight dimming demo

## Technical Notes

### Backlight PWM

When `backlight_pwm=True`, the library uses a 2 kHz PWM signal for smooth dimming:

- **Kernel PWM** (preferred): Uses `/sys/class/pwm` interface — rock-solid timing, no CPU jitter
- **Software PWM** (fallback): Uses `RPi.GPIO.PWM` — may have occasional brightness fluctuations

The library automatically detects and uses kernel PWM when the overlay is enabled.

**Why 2 kHz?** Higher frequencies (5–10 kHz) cause the backlight to appear black at low brightness levels (below 20%). At 2 kHz, all brightness levels work correctly from 0% to 100%.

### Performance

The display runs at 80 MHz SPI by default, achieving ~17 FPS for full-screen updates. If you experience display artifacts, try lowering the speed:

```python
display = DisplayHATMini(spi_speed_hz=52_000_000)  # 52 MHz
```

## Migrating from displayhatmini

Replace:

```python
from displayhatmini import DisplayHATMini
```

With:

```python
from displayhatmini_lite import DisplayHATMini
```

The main API difference: this library doesn't use a numpy buffer. Instead, pass a PIL `Image` directly to `display()`.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [luma.lcd](https://github.com/rm-hull/luma.lcd) for the excellent display driver
- [Pimoroni](https://shop.pimoroni.com/) for the Display HAT Mini hardware
