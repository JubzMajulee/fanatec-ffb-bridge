# ProtoPie → Fanatec FFB Bridge

A small Python app that lets your **ProtoPie prototype drive force feedback on a Fanatec wheel**. ProtoPie Connect sends messages over Socket.IO; this bridge translates them into DirectInput haptic effects on the wheelbase.

No SimHub, no game required. Just ProtoPie Connect, this bridge, and your wheel.

---

## What you can control from ProtoPie

| Message | Value | What it does |
|---|---|---|
| `set_ffb` | `-1.0` to `+1.0` | Pulls the wheel left (−) or right (+). `0` = no force. Smoothly ramps toward the target. |
| `set_ffb_speed` | e.g. `0.5`, `1.0`, `5.0` | How fast `set_ffb` ramps (units/second). `10` ≈ instant. Default `1.0`. |
| `set_vibration` | `0.0` to `1.0` | Wheelbase vibration intensity. Applied immediately. |
| `set_angle` | degrees (e.g. `-90`, `45`) | Parks the wheel at a specific angle. |
| `set_angle_strength` | `0.0` to `1.0` | How firmly `set_angle` holds the wheel. `0` releases it. |

---

## Requirements

- **Windows** (uses DirectInput via SDL2)
- **Python 3.9+** ([python.org](https://www.python.org/downloads/))
- **A Fanatec wheelbase**, plugged in and powered on
- **ProtoPie Connect** running locally on the default port (`9981`)
- **No FanaLab or Fanatec Control Panel actively holding the wheel** — they can grab an exclusive FFB lock that blocks this bridge

---

## Setup

1. Clone or download this folder.

2. Open a terminal in the project folder and create a virtual environment (optional but recommended):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

---

## Run it

1. Plug in and power on your Fanatec wheel.
2. Start **ProtoPie Connect** (it should be listening on `http://localhost:9981`).
3. From the project folder, run:
   ```
   python main.py
   ```

You should see something like:

```
=== ProtoPie -> Fanatec FFB Bridge ===
ProtoPie Connect: http://localhost:9981
Wheel keyword:    fanatec
--------------------------------------
[FFB] 2 joystick(s) detected:
       [0] Fanatec ...
       [1] Fanatec ...
[FFB] Haptic opened on [1] Fanatec ...
[FFB] Constant force armed (signed -1..+1, ramp 1.00/sec)
[FFB] Sine vibration armed (0..1, period=50ms)
[FFB] Centering wheel (1500ms)...
[FFB] Wheel centered
[SocketIO] Connected to http://localhost:9981
```

The wheel will briefly self-center on startup, then sit idle waiting for messages.

Press **Ctrl + C** to stop.

---

## Sending messages from ProtoPie

In your ProtoPie Studio prototype, use a **Send Message** trigger. Set:
- **Message ID:** one of the names from the table above (e.g. `set_ffb`)
- **Value:** the numeric value (e.g. `0.5` to pull right at half strength)

Make sure your ProtoPie prototype is connected to ProtoPie Connect — the bridge listens to whatever Connect broadcasts.

### Quick examples

| You want… | Send | Value |
|---|---|---|
| Strong pull to the right | `set_ffb` | `1.0` |
| Slow drift back to center | `set_ffb` then `set_ffb_speed` | `0.0`, then `0.3` |
| Snappy turn-in | `set_ffb_speed` then `set_ffb` | `8.0`, then `0.7` |
| Buzz the wheel during an alert | `set_vibration` | `0.6` |
| Stop vibrating | `set_vibration` | `0.0` |
| Hold wheel at 30° right | `set_angle` then `set_angle_strength` | `30`, then `0.7` |
| Release the wheel | `set_angle_strength` | `0.0` |

---

## Troubleshooting

**"No joysticks detected"**
The wheel isn't seen by Windows. Check the USB cable, power, and that the wheelbase is fully booted. Try opening Windows' "Set up USB game controllers" — if it doesn't appear there, this bridge can't see it either.

**"None of the candidates would open for haptic"**
Almost always **FanaLab or Fanatec Control Panel** holding an exclusive FFB lock. Close them and run the bridge again. Also: don't run the bridge while a racing game is running.

**"[SocketIO] Failed to connect to http://localhost:9981"**
ProtoPie Connect isn't running, or it's on a different port. Open ProtoPie Connect and confirm the port. If it's different, edit `PROTOPIE_URL` at the top of `main.py`.

**Wheel doesn't react to messages**
Open the bridge's terminal — does each message log a `[ProtoPie] set_ffb -> 0.5` line? If yes, the wheel is the issue (check Fanatec driver / firmware). If no, the message isn't reaching Connect; check that your ProtoPie prototype is actually connected to Connect and using the right `messageId`.

**It picked the wrong device**
By default the bridge opens the first Fanatec device that supports haptic. If you have multiple wheels or unusual setups, change `WHEEL_KEYWORD` in `main.py` to a more specific substring of the device name (case-insensitive).

---

## Optional: Arduino push-button trigger

The `Arduino/pushButtonDemo.ino` sketch lets a **physical button** start the ProtoPie prototype (e.g. kick off the Pie Car navigation simulation that then drives this FFB bridge). The Arduino sends ProtoPie Connect's `messageId||value` serial format, so no extra software is needed in between.

### Wiring

| Arduino | Connect to |
|---|---|
| `A0` | One leg of a momentary push-button |
| `GND` | The other leg of the button |

That's it — `A0` uses the chip's internal pull-up, so no external resistor is required. Any Arduino board with a USB serial connection works (Uno, Nano, Leonardo, Pro Micro, etc.).

### Flashing the sketch

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. Open `Arduino/pushButtonDemo.ino`.
3. **Tools → Board** → select your board.
4. **Tools → Port** → select the COM port the board enumerated as.
5. Click **Upload** (the right-arrow icon).
6. Open **Tools → Serial Monitor** at **9600 baud** and press the button — you should see `Arduino||1` on press and `Arduino||0` on release. Close the Serial Monitor after testing (it holds the COM port).

### Hooking it into ProtoPie Connect

1. In **ProtoPie Connect**, open **Add Device → Serial** (or the equivalent serial input panel for your version).
2. Select the Arduino's COM port and set the baud rate to **9600**.
3. In your ProtoPie Studio prototype, add a **Receive Message** trigger with **Message ID = `Arduino`**. Use the message's value (`1` = pressed, `0` = released) to start your navigation simulation.

Once the prototype is running, pressing the button → emits `Arduino||1` → Connect routes it to ProtoPie → your prototype starts the simulation and begins sending FFB messages (`set_ffb`, `set_vibration`, etc.) → this bridge translates them into wheel force feedback.

---

## Configuration

Edit the top of `main.py`:

```python
PROTOPIE_URL = "http://localhost:9981"   # ProtoPie Connect URL
WHEEL_KEYWORD = "fanatec"                # substring match for the wheel name
```

Defaults inside `FanatecFFB` (in `ffb_driver.py`) you can pass via the constructor:
- `force_ramp_rate=1.0` — default ramp rate for `set_ffb`
- `center_on_start=True` — auto-center the wheel at startup
- `center_duration_ms=1500` — how long the centering spring runs
- `wheel_range_deg=900` — full lock-to-lock range; must match your Fanatec driver setting for `set_angle` to map correctly

---

## How it works (one paragraph)

`main.py` starts a `FanatecFFB` (which opens the wheel via SDL2 and arms a CONSTANT, SINE, and SPRING effect) and a `SocketClient` (which connects to ProtoPie Connect). Each `ppMessage` from Connect is routed by `messageId` to the matching method on `FanatecFFB`, which clamps the value and updates the relevant SDL haptic effect. A background thread interpolates `set_ffb` toward its target at the configured ramp rate so changes feel smooth.

## License

Internal tool — adapt freely for your own ProtoPie prototypes.
