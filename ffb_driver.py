import ctypes
import threading
import time

import sdl2
import sdl2.haptic as haptic


def _sdl_err():
    err = sdl2.SDL_GetError()
    return err.decode() if err else ""


class FanatecFFB:
    DEFAULT_VIBRATION_PERIOD_MS = 50           # ~20 Hz, feels like strong rumble
    DEFAULT_FORCE_RAMP_RATE = 1.0              # units per second (full -1..+1 sweep = 2s)
    DEFAULT_CENTER_DURATION_MS = 1500          # how long to hold the centering spring
    RAMP_TICK_MS = 16                          # ~60 Hz interpolation
    RAMP_EPSILON = 0.0005                      # snap-to-target threshold
    DEFAULT_WHEEL_RANGE_DEG = 900              # full lock-to-lock range set in Fanatec driver
    DEFAULT_ANGLE_COEFF = 16000                # 0..32767, spring stiffness for set_angle
    DEFAULT_ANGLE_SAT = 32767                  # 0..32767, max spring force saturation

    def __init__(
        self,
        wheel_keyword="fanatec",
        force_ramp_rate=DEFAULT_FORCE_RAMP_RATE,
        center_on_start=True,
        center_duration_ms=DEFAULT_CENTER_DURATION_MS,
        wheel_range_deg=DEFAULT_WHEEL_RANGE_DEG,
    ):
        self.wheel_keyword = wheel_keyword.lower()
        self.force_ramp_rate = max(0.001, float(force_ramp_rate))
        self.center_on_start = bool(center_on_start)
        self.center_duration_ms = int(center_duration_ms)
        self.wheel_range_deg = max(90.0, float(wheel_range_deg))

        self.joystick = None
        self.haptic = None

        self.constant_effect = None
        self.constant_id = None

        self.sine_effect = None
        self.sine_id = None

        self.spring_effect = None
        self.spring_id = None
        self.angle_coeff = self.DEFAULT_ANGLE_COEFF

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._ramp_thread = None
        self._target_force = 0.0
        self._current_force = 0.0

        if sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_HAPTIC) < 0:
            print(f"[FFB] SDL init failed: {_sdl_err()}")
            return

        self._open_best_candidate()
        if self.haptic is not None:
            self._arm_effects()
            if self.center_on_start:
                self._center_wheel(self.center_duration_ms)
            self._arm_spring_position()
            if self.constant_id is not None:
                self._ramp_thread = threading.Thread(target=self._ramp_loop, daemon=True)
                self._ramp_thread.start()

    def _open_best_candidate(self):
        count = sdl2.SDL_NumJoysticks()
        if count == 0:
            print("[FFB] No joysticks detected. Is the wheel plugged in and powered on?")
            return

        print(f"[FFB] {count} joystick(s) detected:")
        candidates = []
        for i in range(count):
            name_b = sdl2.SDL_JoystickNameForIndex(i)
            name = name_b.decode() if name_b else f"Joystick {i}"
            print(f"       [{i}] {name}")
            if self.wheel_keyword in name.lower():
                candidates.append((i, name))

        if not candidates:
            name_b = sdl2.SDL_JoystickNameForIndex(0)
            candidates = [(0, name_b.decode() if name_b else "Joystick 0")]
            print(f"[FFB] No match for '{self.wheel_keyword}'. Falling back to [0] {candidates[0][1]}")

        for index, name in candidates:
            print(f"[FFB] Trying [{index}] {name}...")
            joy = sdl2.SDL_JoystickOpen(index)
            if not joy:
                print(f"       SDL_JoystickOpen failed: {_sdl_err()}")
                continue

            if haptic.SDL_JoystickIsHaptic(joy) <= 0:
                print("       No haptic capability on this instance.")
                sdl2.SDL_JoystickClose(joy)
                continue

            hap = haptic.SDL_HapticOpenFromJoystick(joy)
            if not hap:
                print(f"       SDL_HapticOpenFromJoystick failed: {_sdl_err()}")
                sdl2.SDL_JoystickClose(joy)
                continue

            print(f"[FFB] Haptic opened on [{index}] {name}")
            self.joystick = joy
            self.haptic = hap
            return

        print("[FFB] None of the candidates would open for haptic.")
        print("      Common cause: FanaLab / Fanatec Control Panel holds an exclusive FFB lock.")

    def _arm_effects(self):
        supported = haptic.SDL_HapticQuery(self.haptic)
        self._print_supported_effects(supported)

        if supported & haptic.SDL_HAPTIC_CONSTANT:
            self._arm_constant()
        else:
            print("[FFB] CONSTANT not supported — directional force disabled")

        if supported & haptic.SDL_HAPTIC_SINE:
            self._arm_sine()
        else:
            print("[FFB] SINE not supported — vibration disabled")

    def _arm_constant(self):
        eff = haptic.SDL_HapticEffect()
        eff.type = haptic.SDL_HAPTIC_CONSTANT
        eff.constant.type = haptic.SDL_HAPTIC_CONSTANT
        eff.constant.direction.type = haptic.SDL_HAPTIC_CARTESIAN
        eff.constant.direction.dir[0] = 1
        eff.constant.length = haptic.SDL_HAPTIC_INFINITY
        eff.constant.level = 0
        eff.constant.attack_length = 0
        eff.constant.attack_level = 0
        eff.constant.fade_length = 0
        eff.constant.fade_level = 0

        eid = haptic.SDL_HapticNewEffect(self.haptic, ctypes.byref(eff))
        if eid < 0:
            print(f"[FFB] SDL_HapticNewEffect (constant) failed: {_sdl_err()}")
            return
        if haptic.SDL_HapticRunEffect(self.haptic, eid, 1) < 0:
            print(f"[FFB] SDL_HapticRunEffect (constant) failed: {_sdl_err()}")
            haptic.SDL_HapticDestroyEffect(self.haptic, eid)
            return

        self.constant_effect = eff
        self.constant_id = eid
        print(f"[FFB] Constant force armed (signed -1..+1, ramp {self.force_ramp_rate:.2f}/sec)")

    def _arm_spring_position(self):
        if self.haptic is None:
            return

        supported = haptic.SDL_HapticQuery(self.haptic)
        if not (supported & haptic.SDL_HAPTIC_SPRING):
            print("[FFB] SPRING not supported — set_angle disabled")
            return

        eff = haptic.SDL_HapticEffect()
        eff.type = haptic.SDL_HAPTIC_SPRING
        eff.condition.type = haptic.SDL_HAPTIC_SPRING
        eff.condition.direction.type = haptic.SDL_HAPTIC_CARTESIAN
        eff.condition.direction.dir[0] = 0
        eff.condition.length = haptic.SDL_HAPTIC_INFINITY
        eff.condition.delay = 0
        for axis in range(3):
            eff.condition.right_sat[axis] = self.DEFAULT_ANGLE_SAT
            eff.condition.left_sat[axis] = self.DEFAULT_ANGLE_SAT
            # start with coeff=0 so the wheel is free until set_angle is called
            eff.condition.right_coeff[axis] = 0
            eff.condition.left_coeff[axis] = 0
            eff.condition.deadband[axis] = 0
            eff.condition.center[axis] = 0

        eid = haptic.SDL_HapticNewEffect(self.haptic, ctypes.byref(eff))
        if eid < 0:
            print(f"[FFB] SDL_HapticNewEffect (spring position) failed: {_sdl_err()}")
            return
        if haptic.SDL_HapticRunEffect(self.haptic, eid, 1) < 0:
            print(f"[FFB] SDL_HapticRunEffect (spring position) failed: {_sdl_err()}")
            haptic.SDL_HapticDestroyEffect(self.haptic, eid)
            return

        self.spring_effect = eff
        self.spring_id = eid
        print(
            f"[FFB] Spring position armed (range ±{self.wheel_range_deg / 2:.0f}°, "
            f"default coeff {self.DEFAULT_ANGLE_COEFF})"
        )

    def _arm_sine(self):
        eff = haptic.SDL_HapticEffect()
        eff.type = haptic.SDL_HAPTIC_SINE
        eff.periodic.type = haptic.SDL_HAPTIC_SINE
        eff.periodic.direction.type = haptic.SDL_HAPTIC_CARTESIAN
        eff.periodic.direction.dir[0] = 1
        eff.periodic.period = self.DEFAULT_VIBRATION_PERIOD_MS
        eff.periodic.magnitude = 0
        eff.periodic.offset = 0
        eff.periodic.phase = 0
        eff.periodic.length = haptic.SDL_HAPTIC_INFINITY
        eff.periodic.attack_length = 0
        eff.periodic.attack_level = 0
        eff.periodic.fade_length = 0
        eff.periodic.fade_level = 0

        eid = haptic.SDL_HapticNewEffect(self.haptic, ctypes.byref(eff))
        if eid < 0:
            print(f"[FFB] SDL_HapticNewEffect (sine) failed: {_sdl_err()}")
            return
        if haptic.SDL_HapticRunEffect(self.haptic, eid, 1) < 0:
            print(f"[FFB] SDL_HapticRunEffect (sine) failed: {_sdl_err()}")
            haptic.SDL_HapticDestroyEffect(self.haptic, eid)
            return

        self.sine_effect = eff
        self.sine_id = eid
        print(f"[FFB] Sine vibration armed (0..1, period={self.DEFAULT_VIBRATION_PERIOD_MS}ms)")

    def _center_wheel(self, duration_ms, coeff=32767, saturation=32767):
        """One-shot SPRING effect to pull the wheel to center, then release."""
        if self.haptic is None:
            return

        supported = haptic.SDL_HapticQuery(self.haptic)
        if not (supported & haptic.SDL_HAPTIC_SPRING):
            print("[FFB] SPRING not supported — skipping auto-center")
            return

        eff = haptic.SDL_HapticEffect()
        eff.type = haptic.SDL_HAPTIC_SPRING
        eff.condition.type = haptic.SDL_HAPTIC_SPRING
        eff.condition.direction.type = haptic.SDL_HAPTIC_CARTESIAN
        eff.condition.direction.dir[0] = 0
        eff.condition.length = duration_ms
        eff.condition.delay = 0
        for axis in range(3):
            eff.condition.right_sat[axis] = saturation
            eff.condition.left_sat[axis] = saturation
            eff.condition.right_coeff[axis] = coeff
            eff.condition.left_coeff[axis] = coeff
            eff.condition.deadband[axis] = 0
            eff.condition.center[axis] = 0

        eid = haptic.SDL_HapticNewEffect(self.haptic, ctypes.byref(eff))
        if eid < 0:
            print(f"[FFB] SDL_HapticNewEffect (spring) failed: {_sdl_err()}")
            return

        if haptic.SDL_HapticRunEffect(self.haptic, eid, 1) < 0:
            print(f"[FFB] SDL_HapticRunEffect (spring) failed: {_sdl_err()}")
            haptic.SDL_HapticDestroyEffect(self.haptic, eid)
            return

        print(f"[FFB] Centering wheel ({duration_ms}ms)...")
        time.sleep(duration_ms / 1000.0 + 0.2)

        haptic.SDL_HapticStopEffect(self.haptic, eid)
        haptic.SDL_HapticDestroyEffect(self.haptic, eid)
        print("[FFB] Wheel centered")

    @staticmethod
    def _print_supported_effects(mask):
        flags = [
            ("CONSTANT", haptic.SDL_HAPTIC_CONSTANT),
            ("SINE", haptic.SDL_HAPTIC_SINE),
            ("TRIANGLE", haptic.SDL_HAPTIC_TRIANGLE),
            ("SAWTOOTHUP", haptic.SDL_HAPTIC_SAWTOOTHUP),
            ("SAWTOOTHDOWN", haptic.SDL_HAPTIC_SAWTOOTHDOWN),
            ("RAMP", haptic.SDL_HAPTIC_RAMP),
            ("SPRING", haptic.SDL_HAPTIC_SPRING),
            ("DAMPER", haptic.SDL_HAPTIC_DAMPER),
            ("INERTIA", haptic.SDL_HAPTIC_INERTIA),
            ("FRICTION", haptic.SDL_HAPTIC_FRICTION),
            ("CUSTOM", haptic.SDL_HAPTIC_CUSTOM),
        ]
        present = [n for n, b in flags if mask & b]
        print(f"[FFB] Supported effects: {', '.join(present) if present else '(none)'}")

    @staticmethod
    def _clamp(value, min_val, max_val):
        try:
            v = float(value)
        except (TypeError, ValueError):
            print(f"[FFB] Invalid value '{value}', defaulting to {min_val}")
            return min_val
        return max(min_val, min(max_val, v))

    def _ramp_loop(self):
        tick_seconds = self.RAMP_TICK_MS / 1000.0
        last = time.monotonic()
        while not self._stop_event.is_set():
            time.sleep(tick_seconds)
            now = time.monotonic()
            elapsed = now - last
            last = now

            with self._lock:
                if self.constant_id is None:
                    continue
                diff = self._target_force - self._current_force
                if abs(diff) < self.RAMP_EPSILON:
                    if self._current_force != self._target_force:
                        self._current_force = self._target_force
                        self._write_constant_locked(self._current_force)
                    continue

                max_step = self.force_ramp_rate * elapsed
                if abs(diff) <= max_step:
                    self._current_force = self._target_force
                else:
                    self._current_force += max_step if diff > 0 else -max_step
                self._write_constant_locked(self._current_force)

    def _write_constant_locked(self, normalized):
        level = int(normalized * 32767)
        self.constant_effect.constant.level = level
        rc = haptic.SDL_HapticUpdateEffect(
            self.haptic, self.constant_id, ctypes.byref(self.constant_effect)
        )
        if rc < 0:
            print(f"[FFB] Update constant failed: {_sdl_err()}")

    def set_force(self, value):
        """Directional force. Ramps from current toward target at force_ramp_rate units/sec."""
        if self.constant_id is None:
            print("[FFB] Constant effect not armed, ignoring set_force")
            return False
        clamped = self._clamp(value, -1.0, 1.0)
        with self._lock:
            from_value = self._current_force
            self._target_force = clamped
        print(
            f"[FFB] force target = {clamped:+.3f} "
            f"(from {from_value:+.3f}, rate {self.force_ramp_rate:.2f}/sec)"
        )
        return True

    def set_force_speed(self, rate):
        """Update the ramp rate (units per second). 0.5 = slow, 2.0 = fast, 10.0+ ≈ instant."""
        try:
            r = max(0.001, float(rate))
        except (TypeError, ValueError):
            print(f"[FFB] Invalid ramp rate '{rate}', ignoring")
            return False
        with self._lock:
            self.force_ramp_rate = r
        print(f"[FFB] force ramp rate set to {r:.2f}/sec")
        return True

    def set_vibration(self, value, period_ms=None):
        """Sine vibration intensity (0..1). Applied immediately, no ramping."""
        if self.sine_id is None:
            print("[FFB] Sine effect not armed, ignoring set_vibration")
            return False

        clamped = self._clamp(value, 0.0, 1.0)
        magnitude = int(clamped * 32767)
        with self._lock:
            self.sine_effect.periodic.magnitude = magnitude
            if period_ms is not None:
                try:
                    self.sine_effect.periodic.period = max(1, int(period_ms))
                except (TypeError, ValueError):
                    pass

            rc = haptic.SDL_HapticUpdateEffect(
                self.haptic, self.sine_id, ctypes.byref(self.sine_effect)
            )
            if rc < 0:
                print(f"[FFB] Update sine failed: {_sdl_err()}")
                return False
            period = self.sine_effect.periodic.period
        print(f"[FFB] vibration = {clamped:.3f} (magnitude={magnitude}, period={period}ms)")
        return True

    def set_angle(self, degrees):
        """Park the wheel at `degrees` (+right / -left) via spring effect.
        Range is clamped to ±wheel_range_deg/2."""
        if self.spring_id is None:
            print("[FFB] Spring effect not armed, ignoring set_angle")
            return False

        half_range = self.wheel_range_deg / 2.0
        clamped_deg = self._clamp(degrees, -half_range, half_range)
        center = int((clamped_deg / half_range) * 32767)

        with self._lock:
            coeff = self.angle_coeff
            for axis in range(3):
                self.spring_effect.condition.center[axis] = center
                self.spring_effect.condition.right_coeff[axis] = coeff
                self.spring_effect.condition.left_coeff[axis] = coeff
            rc = haptic.SDL_HapticUpdateEffect(
                self.haptic, self.spring_id, ctypes.byref(self.spring_effect)
            )
            if rc < 0:
                print(f"[FFB] Update spring position failed: {_sdl_err()}")
                return False
        print(f"[FFB] angle = {clamped_deg:+.1f}° (center={center}, coeff={coeff})")
        return True

    def set_angle_strength(self, strength):
        """Spring stiffness for set_angle. 0..1 -> coeff 0..32767.
        0 releases the wheel entirely; 1 is maximum resistance."""
        if self.spring_id is None:
            print("[FFB] Spring effect not armed, ignoring set_angle_strength")
            return False

        s = self._clamp(strength, 0.0, 1.0)
        coeff = int(s * 32767)
        with self._lock:
            self.angle_coeff = coeff
            for axis in range(3):
                self.spring_effect.condition.right_coeff[axis] = coeff
                self.spring_effect.condition.left_coeff[axis] = coeff
            rc = haptic.SDL_HapticUpdateEffect(
                self.haptic, self.spring_id, ctypes.byref(self.spring_effect)
            )
            if rc < 0:
                print(f"[FFB] Update spring strength failed: {_sdl_err()}")
                return False
        print(f"[FFB] angle strength = {s:.2f} (coeff={coeff})")
        return True

    def stop(self):
        self._stop_event.set()
        if self._ramp_thread is not None:
            self._ramp_thread.join(timeout=1.0)
            self._ramp_thread = None

        if self.haptic is not None:
            for eid in (self.constant_id, self.sine_id, self.spring_id):
                if eid is None:
                    continue
                try:
                    haptic.SDL_HapticStopEffect(self.haptic, eid)
                    haptic.SDL_HapticDestroyEffect(self.haptic, eid)
                except Exception as e:
                    print(f"[FFB] Cleanup error (effect {eid}): {e}")
            try:
                haptic.SDL_HapticClose(self.haptic)
            except Exception as e:
                print(f"[FFB] Cleanup error (haptic): {e}")
            self.haptic = None
            self.constant_id = None
            self.sine_id = None
            self.spring_id = None
            self.constant_effect = None
            self.sine_effect = None
            self.spring_effect = None

        if self.joystick is not None:
            try:
                sdl2.SDL_JoystickClose(self.joystick)
            except Exception as e:
                print(f"[FFB] Cleanup error (joystick): {e}")
            self.joystick = None

        sdl2.SDL_Quit()
