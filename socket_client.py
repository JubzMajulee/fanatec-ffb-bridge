import threading
import time

import socketio


class SocketClient:
    def __init__(self, url, ffb_driver):
        self.url = url
        self.ffb_driver = ffb_driver
        self._stop = threading.Event()
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_delay=2,
            reconnection_delay_max=10,
        )
        self._register_handlers()

    def _register_handlers(self):
        @self.sio.event
        def connect():
            print(f"[SocketIO] Connected to {self.url}")

        @self.sio.event
        def disconnect():
            print("[SocketIO] Disconnected from ProtoPie Connect")

        @self.sio.event
        def connect_error(data):
            print(f"[SocketIO] Connection error: {data}")

        # ProtoPie Connect standard event: { messageId, value }
        @self.sio.on("ppMessage")
        def on_pp_message(data):
            self._handle_pp_message(data)

        # Fallback: some setups emit messageId directly as the event name
        @self.sio.on("set_ffb")
        def on_set_ffb(data):
            value = self._extract_value(data)
            print(f"[ProtoPie] set_ffb -> {value}")
            self.ffb_driver.set_force(value)

        @self.sio.on("set_vibration")
        def on_set_vibration(data):
            value = self._extract_value(data)
            print(f"[ProtoPie] set_vibration -> {value}")
            self.ffb_driver.set_vibration(value)

        @self.sio.on("set_ffb_speed")
        def on_set_ffb_speed(data):
            value = self._extract_value(data)
            print(f"[ProtoPie] set_ffb_speed -> {value}")
            self.ffb_driver.set_force_speed(value)

        @self.sio.on("set_angle")
        def on_set_angle(data):
            value = self._extract_value(data)
            print(f"[ProtoPie] set_angle -> {value}")
            self.ffb_driver.set_angle(value)

        @self.sio.on("set_angle_strength")
        def on_set_angle_strength(data):
            value = self._extract_value(data)
            print(f"[ProtoPie] set_angle_strength -> {value}")
            self.ffb_driver.set_angle_strength(value)

    def _handle_pp_message(self, data):
        if not isinstance(data, dict):
            return
        message_id = data.get("messageId")
        value = data.get("value")

        if message_id == "set_ffb":
            print(f"[ProtoPie] ppMessage set_ffb -> {value}")
            self.ffb_driver.set_force(value)
        elif message_id == "set_vibration":
            print(f"[ProtoPie] ppMessage set_vibration -> {value}")
            self.ffb_driver.set_vibration(value)
        elif message_id == "set_ffb_speed":
            print(f"[ProtoPie] ppMessage set_ffb_speed -> {value}")
            self.ffb_driver.set_force_speed(value)
        elif message_id == "set_angle":
            print(f"[ProtoPie] ppMessage set_angle -> {value}")
            self.ffb_driver.set_angle(value)
        elif message_id == "set_angle_strength":
            print(f"[ProtoPie] ppMessage set_angle_strength -> {value}")
            self.ffb_driver.set_angle_strength(value)

    @staticmethod
    def _extract_value(data):
        if isinstance(data, dict):
            return data.get("value", 0.0)
        return data

    def connect(self):
        try:
            self.sio.connect(self.url)
        except Exception as e:
            print(f"[SocketIO] Failed to connect to {self.url}: {e}")
            return False
        return True

    def wait(self):
        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n[SocketIO] Interrupted by user, shutting down")
        finally:
            self._stop.set()
            if self.sio.connected:
                try:
                    self.sio.disconnect()
                except Exception as e:
                    print(f"[SocketIO] Error during disconnect: {e}")

    def stop(self):
        self._stop.set()
