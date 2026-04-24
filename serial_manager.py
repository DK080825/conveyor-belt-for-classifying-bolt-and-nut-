import time
import threading

try:
    import serial
except Exception:
    serial = None


class SerialManager:
    def __init__(self, port="COM3", baud=115200, mock=False):
        self.port = port
        self.baud = baud
        self.mock = mock

        self.ser = None
        self.callback = None

        self.last_cmd = None
        self.ack_event = threading.Event()
        self._send_lock = threading.Lock()

        self._stop_evt = threading.Event()
        self._reader = threading.Thread(target=self._reader_thread, daemon=True)

        if not self.mock:
            self.open()

        self._reader.start()

    def set_callback(self, cb):
        self.callback = cb

    # ---- for GUI status ----
    def is_open(self):
        if self.mock:
            return True
        return self.ser is not None and getattr(self.ser, "is_open", False)

    def open(self):
        if self.mock:
            return True
        if serial is None:
            return False
        try:
            if self.ser and self.ser.is_open:
                return True
            self.ser = serial.Serial(self.port, self.baud, timeout=0.01)
            return True
        except Exception:
            self.ser = None
            return False

    # ---------------- Reader ----------------
    def _reader_thread(self):
        buffer = b""
        while not self._stop_evt.is_set():
            if self.ser:
                try:
                    data = self.ser.read(64)
                except Exception:
                    data = b""

                if data:
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        text = line.decode(errors="ignore").strip()

                        # ACK check
                        if self.last_cmd and self._is_ack_for(text, self.last_cmd):
                            self.ack_event.set()

                        if self.callback:
                            self.callback(text)

            time.sleep(0.002)

    def _is_ack_for(self, line, cmd):
        # cmd_key -> ack string
        ack_map = {
            "start_conveyor": "ACK_START",
            "stop_conveyor": "ACK_STOP",
            "SET_SPEED": "ACK_SET_SPEED",
            "bolt_detect": "ACK_BOLT",
            "nut_detect": "ACK_NUT",
        }

        # giữ đúng nội dung cmd (không upper/lower toàn bộ)
        for key, ack in ack_map.items():
            if cmd.startswith(key):
                return line.startswith(ack)

        return False

    def _send_with_ack(self, msg, timeout=1.0):
        # đảm bảo gửi đúng y nguyên msg bạn đưa vào
        if self.mock:
            return True
        if not self.is_open():
            return False

        # chặn gửi song song để ACK không bị lạc
        with self._send_lock:
            self.last_cmd = msg
            self.ack_event.clear()

            try:
                self.ser.write((msg + "\n").encode("utf-8", errors="ignore"))
            except Exception:
                return False

            return self.ack_event.wait(timeout=timeout)

    # ---------------- Public API (GIỮ Y NGUYÊN) ----------------
    def send_start_conveyor(self):
        return self._send_with_ack("start_conveyor")

    def send_stop_conveyor(self):
        return self._send_with_ack("stop_conveyor")

    def send_set_speed(self, speed):
        return self._send_with_ack(f"SET_SPEED:{speed}")

    def send_bolt_detect(self):
        return self._send_with_ack("bolt_detect", timeout=0.25)

    def send_nut_detect(self):
        return self._send_with_ack("nut_detect", timeout=0.25)

    def close(self):
        self._stop_evt.set()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
