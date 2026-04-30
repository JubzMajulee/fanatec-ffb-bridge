# Session Notes — ProtoPie ↔ Fanatec FFB Bridge

_Last updated: 2026-04-23_

## Where we are

Working Python middleware that drives Fanatec wheel FFB **directly** from ProtoPie Connect over Socket.IO. **SimHub is no longer in the loop** — the bridge talks straight to the wheel via SDL2 haptic.

## Architecture

```
ProtoPie Connect (Socket.IO @ localhost:9981)
        │   ppMessage { messageId, value }
        ▼
SocketClient  ─────►  FanatecFFB (PySDL2 haptic)
                            │
                            ▼  DirectInput FFB
                      Fanatec wheelbase
```

### Files
| File | Role |
|---|---|
| `main.py` | Entry point. Wires `FanatecFFB` into `SocketClient`. |
| `socket_client.py` | Socket.IO listener for ProtoPie messages. |
| `ffb_driver.py` | SDL2 haptic driver — manages CONSTANT, SINE, and centering SPRING effects. |
| `requirements.txt` | `python-socketio[client]`, `pysdl2`, `pysdl2-dll` |

### Run it
```
pip install -r requirements.txt
python main.py
```

## ProtoPie message contract

The bridge listens for `ppMessage` events from ProtoPie Connect with `{ messageId, value }`.

| `messageId` | `value` range | Behavior |
|---|---|---|
| `set_ffb` | `-1.0` … `+1.0` | Directional constant force. **Ramps** from current to target (does not snap). `-1.0` = full left, `0.0` = slack, `+1.0` = full right. |
| `set_ffb_speed` | units/sec, e.g. `0.5`, `1.0`, `5.0` | Tunes how fast `set_ffb` ramps. Lower = slower glide. `10.0+` ≈ instant. Default `1.0`. |
| `set_vibration` | `0.0` … `1.0` | Sine-wave wheelbase vibration. Applied immediately, no ramping. |

## Startup sequence

1. Enumerates all joysticks; collects every device whose name contains `fanatec`.
2. Iterates candidates, opens the first one where `SDL_HapticOpenFromJoystick` succeeds. _(Fanatec exposes two DirectInput devices — FFB only works on one of them, typically index `[1]`.)_
3. Arms a CONSTANT force effect (level 0) and a SINE periodic effect (magnitude 0).
4. Applies a strong SPRING effect for 1.5s to **physically center the wheel**, then releases it.
5. Starts the ~60 Hz ramp thread that interpolates `set_ffb` toward its target.
6. Connects to ProtoPie Connect; ready for messages.

## Key decisions and gotchas

- **Why no SimHub:** SimHub's `/api/property/{name}` is **GET-only** — vanilla SimHub has no built-in POST endpoint to write property values. The JavaScriptExtensions folder is for NCalc/dashboard scripts, not HTTP routing (`SimHub.Http.RegisterPost` is not a real API).
- **Why no pygame:** `pygame.joystick.rumble()` returned `not supported` on the Fanatec wheel. The fix was to use SDL2's full Haptic API with the `CONSTANT` effect type — same effect racing games use.
- **Two Fanatec DirectInput devices:** the first refused haptic open; the second worked. The driver tries each candidate, so this is auto-handled — don't hard-code an index.
- **Constant + Sine run simultaneously** so directional force and vibration are independent channels.
- **Centering is one-shot at startup** — after the SPRING effect ends, only your `set_ffb` and `set_vibration` are active. The spring isn't kept on (it would fight `set_ffb`).

## Tunables in `main.py`

```python
PROTOPIE_URL = "http://localhost:9981"
WHEEL_KEYWORD = "fanatec"
```

In `FanatecFFB(...)` constructor (currently using defaults):
- `force_ramp_rate=1.0` — default ramp speed
- `center_on_start=True` — auto-center on launch
- `center_duration_ms=1500` — how long the centering spring runs

## Possible next steps (not implemented)

- **`set_vibration_period`** message to control vibration frequency from ProtoPie.
- **Mid-session `recenter` message** — would need to coordinate with the running constant force.
- **Auto-center spring kept on** as an "always returns to zero" mode.
- **Raw DirectInput via ctypes** as a fallback if SDL2 haptic ever stops working.
- **Signed-direction vibration** (currently sine direction is fixed; could mix with constant).
