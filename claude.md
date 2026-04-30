# Project: ProtoPie to Fanatec FFB Bridge

## Goal
Python middleware that bridges ProtoPie Connect to a Fanatec wheelbase, driving force feedback **directly** via SDL2's DirectInput haptic API. SimHub is **not** in the loop (its `/api/property/{name}` endpoint is GET-only — there's no built-in POST to write property values).

## Tech Stack
- Language: Python 3.x
- Communication: Socket.IO client (`python-socketio[client]`) listening to ProtoPie Connect at `http://localhost:9981`
- FFB: PySDL2 (`pysdl2`, `pysdl2-dll`) — SDL2 haptic effects (CONSTANT, SINE, SPRING)

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
| `socket_client.py` | Socket.IO listener for ProtoPie `ppMessage` events. |
| `ffb_driver.py` | SDL2 haptic driver: arms CONSTANT (directional force), SINE (vibration), SPRING (position/centering). |
| `requirements.txt` | `python-socketio[client]`, `pysdl2`, `pysdl2-dll` |

## ProtoPie message contract
Listens for `ppMessage` events with `{ messageId, value }`. Also accepts the `messageId` directly as the event name as a fallback.

| `messageId` | `value` range | Behavior |
|---|---|---|
| `set_ffb` | `-1.0 … +1.0` | Directional constant force, ramped over time. `-1` = full left, `0` = slack, `+1` = full right. |
| `set_ffb_speed` | units/sec (`0.5`, `1.0`, `5.0`, …) | Ramp rate for `set_ffb`. `10.0+` ≈ instant. Default `1.0`. |
| `set_vibration` | `0.0 … 1.0` | Sine wheelbase vibration intensity. Applied immediately. |
| `set_angle` | degrees, `±wheel_range_deg/2` | Parks the wheel at this angle via SPRING. |
| `set_angle_strength` | `0.0 … 1.0` | Spring stiffness for `set_angle`. `0` releases the wheel. |

## Coding Guidelines
- **Modularity**: Keep `SocketClient` (transport) separate from `FanatecFFB` (hardware). `main.py` only wires them together.
- **Clamping**: All inbound values are clamped to their valid range inside `FanatecFFB` before reaching SDL.
- **Robustness**: Guard SDL calls and wrap reconnection logic; the Socket.IO client uses built-in auto-reconnect.
- **Logging**: Use clear `print()` statements prefixed with `[FFB]`, `[SocketIO]`, or `[ProtoPie]` so the source of each line is obvious.

## Gotchas
- Fanatec exposes **two DirectInput devices**; haptic typically opens only on the second. The driver iterates candidates matching `WHEEL_KEYWORD` ("fanatec") and opens the first one whose `SDL_HapticOpenFromJoystick` succeeds — don't hard-code an index.
- FanaLab / Fanatec Control Panel can hold an **exclusive FFB lock**. If haptic open fails on every candidate, that's the most common cause.
- `pygame.joystick.rumble()` does not work with Fanatec — that's why this project uses SDL2 haptic directly.
- Centering is **one-shot at startup** (1.5 s SPRING, then released). The spring is not kept on — it would fight `set_ffb`.
