# ============================================================
# conveyor_gui.py — Conveyor Vision Dashboard (Styled GUI)
# ============================================================

import sys
import time
import argparse
import cv2
from ultralytics import YOLO

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QMessageBox
)

from serial_manager import SerialManager



# ============================================================
# YOLO Worker Thread (GIỮ NGUYÊN LOGIC — KHÔNG ĐỤNG)
# ============================================================
class YOLOWorker(QThread):
    frameReady = pyqtSignal(QImage)
    statsUpdated = pyqtSignal(float, float)     # FPS, Latency(ms)
    screwCountUpdated = pyqtSignal(int, int)    # bolt_count, nut_count
    logMessage = pyqtSignal(str)

    # State machine
    WAIT_PRE  = 0   # chờ thấy vật thể ở vùng trước line
    WAIT_POST = 1   # đã thấy PRE, chờ thấy vật thể ở vùng sau line + margin

    def __init__(self, model_path, serial_mgr):
        super().__init__()
        self.model_path = model_path
        self.serial = serial_mgr

        self.running = True
        self.conveyor_active = False

        self.bolt_count = 0
        self.nut_count = 0

        # ===== Camera / inference =====
        self.conf_thres = 0.5
        self.resize_w = 960
        self.resize_h = 540

        # ===== Trigger logic (tối ưu cho băng chuyền nhanh) =====
        self.trigger_y = 270

        # PRE/POST margin: “một khoảng” trước/sau trigger line
        # - pre_margin nhỏ hơn post_margin để dễ "arming"
        # - post_margin đủ lớn để chắc chắn đã qua line, chống jitter
        self.pre_margin  = 5     # px
        self.post_margin = 15    # px

        # Debounce: cần thấy ổn định vài lần trong vùng để xác nhận
        self.pre_hits_required  = 2
        self.post_hits_required = 2

        # Miss tolerance: cho phép YOLO mất vài frame mà không reset state
        self.reset_after_miss = 46
        self.miss_frames = 0

        # State variables
        self.state = self.WAIT_PRE
        self.pre_hits = 0
        self.post_hits = 0
        self.armed_cls = None  # lưu class đã thấy ở PRE (0 bolt, 1 nut)

        # FPS smoothing
        self._fps_ema = 0.0
        self._last_loop_t = time.time()

    def set_conveyor_active(self, active: bool):
        self.conveyor_active = active
        self.logMessage.emit(f"[INFO] Conveyor active = {active}")

        if not active:
            # reset state để tránh đếm lạc khi stop/start
            self._reset_trigger_state(full=True)

    def stop(self):
        self.running = False

    def _reset_trigger_state(self, full: bool = False):
        """Reset state machine; full=True thì reset thêm miss."""
        self.state = self.WAIT_PRE
        self.pre_hits = 0
        self.post_hits = 0
        self.armed_cls = None
        if full:
            self.miss_frames = 0

    def _choose_one_object(self, valid, trigger_y):
        """
        valid: list of (cls, conf, x1,y1,x2,y2)
        Vì giả thiết 1 vật thể/lượt, ta chọn box có bottom_y gần trigger nhất.
        Điều này giúp ổn định theo thời gian hơn chọn bottom_y lớn nhất.
        """
        # ưu tiên gần trigger (giảm bỏ qua khi vật thể vừa qua line)
        return min(valid, key=lambda t: abs(t[5] - trigger_y))

    def run(self):
        # ----- Load model -----
        try:
            self.logMessage.emit("[INFO] Loading YOLO model...")
            model = YOLO(self.model_path).to("cuda")
            self.logMessage.emit("[INFO] YOLO loaded.")
        except Exception as e:
            self.logMessage.emit(f"[ERROR] YOLO load failed: {e}")
            return

        # ----- Open camera -----
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.logMessage.emit("[ERROR] Camera open failed")
            return

        while self.running:
            ok, frame = cap.read()
            if not ok or frame is None:
                self.msleep(5)
                continue

            display = cv2.resize(frame, (self.resize_w, self.resize_h))
            h, w = self.resize_h, self.resize_w

            # ----- Draw trigger line + zones -----
            y = self.trigger_y
            y_pre  = max(0, y - self.pre_margin)
            y_post = min(h - 1, y + self.post_margin)

            # background for trigger region (optional)
            overlay = display.copy()
            cv2.rectangle(overlay, (0, y), (w, h), (255, 200, 120), -1)
            display = cv2.addWeighted(overlay, 0.16, display, 0.84, 0)

            # lines
            cv2.line(display, (0, y), (w, y), (0, 180, 255), 2)            # trigger
            cv2.line(display, (0, y_pre), (w, y_pre), (80, 80, 220), 1)    # pre boundary
            cv2.line(display, (0, y_post), (w, y_post), (80, 220, 80), 1)  # post boundary

            fps = 0.0
            latency = 0.0

            if self.conveyor_active:
                # ----- YOLO inference latency (ms) -----
                t0 = time.time()
                results = model(display, verbose=False)[0]
                latency = (time.time() - t0) * 1000.0

                # ----- Collect valid detections -----
                valid = []
                for box in results.boxes:
                    cls = int(box.cls)
                    conf = float(box.conf)
                    if cls not in (0, 1) or conf < self.conf_thres:
                        continue
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    valid.append((cls, conf, x1, y1, x2, y2))

                seen = len(valid) > 0

                if seen:
                    self.miss_frames = 0

                    # chọn 1 vật thể đại diện (giả thiết 1 vật thể/lượt)
                    cls, conf, x1, y1b, x2, y2 = self._choose_one_object(valid, self.trigger_y)
                    bottom_y = int(y2)

                    # Draw box
                    name = "Bolt" if cls == 0 else "Nut"
                    cv2.rectangle(display, (x1, y1b), (x2, y2), (78, 201, 176), 2)
                    cv2.putText(
                        display, f"{name} {conf:.2f}",
                        (x1, max(0, y1b - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (78, 201, 176), 2
                    )

                    # ----- Zone classify -----
                    in_pre  = (bottom_y < y_pre)
                    in_post = (bottom_y > y_post)
                    # vùng giữa (gần trigger) không quyết định, chỉ để vật thể "đi qua"

                    # ====== STATE MACHINE: PRE then POST ======
                    if self.state == self.WAIT_PRE:
                        if in_pre:
                            self.pre_hits += 1
                            # lưu class “được xác nhận” (để tránh lẫn bolt/nut)
                            if self.armed_cls is None:
                                self.armed_cls = cls
                            else:
                                # nếu rung class, ưu tiên giữ class ban đầu trong PRE
                                pass

                            if self.pre_hits >= self.pre_hits_required:
                                self.state = self.WAIT_POST
                                self.post_hits = 0
                                # log nhẹ (tùy bạn bật/tắt)
                                # self.logMessage.emit(f"[TRG] Armed {('Bolt' if self.armed_cls==0 else 'Nut')}")

                        else:
                            # chưa vào PRE zone thì không tăng hit
                            # (không reset để tránh rung)
                            pass

                    elif self.state == self.WAIT_POST:
                        # Nếu mất vật thể quá lâu -> reset
                        # (handled by miss_frames branch)

                        # Nếu đã vào POST zone thì xác nhận và đếm
                        if in_post:
                            # chỉ đếm nếu cls khớp class đã armed (giảm sai loại)
                            # nếu bạn muốn “miễn khớp class”, bỏ điều kiện này
                            if self.armed_cls is None or cls == self.armed_cls:
                                self.post_hits += 1
                            else:
                                # class mismatch -> không tăng post_hits
                                pass

                            if self.post_hits >= self.post_hits_required:
                                if self.armed_cls == 0:
                                    self.bolt_count += 1
                                    self.serial.send_bolt_detect()
                                else:
                                    self.nut_count += 1
                                    self.serial.send_nut_detect()

                                self.screwCountUpdated.emit(self.bolt_count, self.nut_count)

                                # reset để chờ vật thể tiếp theo
                                self._reset_trigger_state(full=True)

                        else:
                            # chưa đến POST zone thì chờ tiếp
                            pass

                else:
                    # ===== Miss tolerance =====
                    self.miss_frames += 1
                    if self.miss_frames >= self.reset_after_miss:
                        # mất detect đủ lâu -> reset state
                        self._reset_trigger_state(full=True)

                # ----- FPS of loop (pipeline FPS) -----
                now = time.time()
                dt = now - self._last_loop_t
                if dt > 0:
                    inst = 1.0 / dt
                    self._fps_ema = (0.85 * self._fps_ema) + (0.15 * inst)
                    fps = self._fps_ema
                self._last_loop_t = now

            # ----- Convert frame for GUI -----
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)

            self.frameReady.emit(qimg.copy())
            self.statsUpdated.emit(float(fps), float(latency))
            self.msleep(5)

        cap.release()
        self.logMessage.emit("[INFO] YOLOWorker stopped")

# ============================================================
# MAIN WINDOW
# ============================================================
class ConveyorWindow(QMainWindow):

    def __init__(self, model_path, port, baud, mock=False):
        super().__init__()

        self.serial = SerialManager(port, baud, mock)
        self.serial.set_callback(self.on_serial)
        self.init_ui()
        
        if not self.serial.open():
            self.log("[WARN] Serial open failed (check COM port)")

        self.yolo = YOLOWorker(model_path, self.serial)
        self.yolo.frameReady.connect(self.update_frame)
        self.yolo.statsUpdated.connect(self.update_stats)
        self.yolo.screwCountUpdated.connect(self.update_counts)
        self.yolo.logMessage.connect(self.log)

        self.conveyor_running = False


         # ===== COM STATUS TIMER =====
        self._last_com_state = None
        self.com_timer = QTimer(self)
        self.com_timer.timeout.connect(self.update_com_status)
        self.com_timer.start(300)  # 300ms là đủ mượt
        self.update_com_status()   # cập nhật ngay lập tức

        self.yolo.start()


    def update_com_status(self):
        connected = self.serial.is_open()
        if connected == self._last_com_state:
            return
        self._last_com_state = connected

        if connected:
            self.lbl_com.setText(f"🟢 COM: Connected ({self.serial.port})")
            self.lbl_com.setStyleSheet("""
                QLabel {
                    color: #ECF0F1;
                    background: #1F6F43;
                    padding: 6px 10px;
                    border-radius: 8px;
                }
            """)
        else:
            self.lbl_com.setText(f"🔴 COM: Disconnected ({self.serial.port})")
            self.lbl_com.setStyleSheet("""
                QLabel {
                    color: #ECF0F1;
                    background: #7A2E2E;
                    padding: 6px 10px;
                    border-radius: 8px;
                }
            """)
    # ========================================================
    # STYLE HELPERS (CHỈ GUI)
    # ========================================================
    def style_button(self, btn, bg):
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:disabled {{
                background-color: #555;
                color: #AAA;
            }}
        """)

    # ========================================================
    # UI
    # ========================================================
    def init_ui(self):
        self.setWindowTitle("Conveyor Vision Dashboard")
        self.resize(1280, 720)

        font_small = QFont("Segoe UI", 11)
        font_counter = QFont("Segoe UI", 22, QFont.Bold)

        central = QWidget()
        central.setStyleSheet("background:#1E1F26;")
        self.setCentralWidget(central)

        main = QVBoxLayout(central)

        # ================= TOP =================
        top = QHBoxLayout()

        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_reset = QPushButton("Reset")

        self.style_button(self.btn_start, "#27AE60")
        self.style_button(self.btn_stop, "#C0392B")
        self.style_button(self.btn_reset, "#2980B9")

        self.btn_stop.setEnabled(False)

        self.btn_start.clicked.connect(self.handle_start)
        self.btn_stop.clicked.connect(self.handle_stop)
        self.btn_reset.clicked.connect(self.handle_reset)
        
         # ==== COM STATUS (góc trái) ====
        self.lbl_com = QLabel("🔴 COM: Disconnected")
        self.lbl_com.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_com.setStyleSheet("""
            QLabel {
                color: #ECF0F1;
                background: #2C2F3A;
                padding: 6px 10px;
                border-radius: 8px;
            }
        """)
        top.addWidget(self.lbl_com)
        top.addSpacing(10)

        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_reset)
        top.addStretch()
        main.addLayout(top)

        # ================= VIDEO =================
        self.lbl_video = QLabel()
        self.lbl_video.setFixedSize(960, 540)
        self.lbl_video.setStyleSheet("background:black;")
        main.addWidget(self.lbl_video, alignment=Qt.AlignCenter)

        # ================= BOTTOM =================
        bottom = QHBoxLayout()

        left = QVBoxLayout()
        self.speed_input = QLineEdit()
        self.speed_input.setPlaceholderText("Speed 0–100")
        self.speed_input.setStyleSheet("""
            background:#2C2F3A;
            color:#ECF0F1;
            padding:6px;
            border-radius:4px;
        """)

        btn_speed = QPushButton("Set Speed")
        self.style_button(btn_speed, "#8E44AD")
        btn_speed.clicked.connect(self.handle_set_speed)

        self.lbl_speed = QLabel("Current Speed: 0 RPM")
        self.lbl_fps = QLabel("FPS: 0.0")
        self.lbl_latency = QLabel("Latency: 0.0 ms")

        for w in (self.lbl_speed, self.lbl_fps, self.lbl_latency):
            w.setFont(font_small)
            w.setStyleSheet("color:#ECF0F1;")

        self.lbl_bolt = QLabel("Bolt Count: 0")
        self.lbl_bolt.setFont(font_counter)
        self.lbl_bolt.setStyleSheet("color:#4EC9B0;")

        self.lbl_nut = QLabel("Nut Count: 0")
        self.lbl_nut.setFont(font_counter)
        self.lbl_nut.setStyleSheet("color:#F1C40F;")

        left.addWidget(self.speed_input)
        left.addWidget(btn_speed)
        left.addWidget(self.lbl_speed)
        left.addWidget(self.lbl_fps)
        left.addWidget(self.lbl_latency)
        left.addStretch()
        left.addWidget(self.lbl_bolt)
        left.addWidget(self.lbl_nut)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background:#11141A;color:#ECF0F1;")

        bottom.addLayout(left, 1)
        bottom.addWidget(self.txt_log, 2)
        main.addLayout(bottom)

    # ========================================================
    # ACK-AWARE COMMAND HANDLING
    # ========================================================
    def send_cmd_with_log(self, cmd, send_func, ack_name):
        self.log(f"[CMD] {cmd} sent")
        ok = send_func()
        if not ok:
            self.log(f"[ERROR] No {ack_name}")
            return False
        self.log(f"[ACK] {ack_name} received")
        return True

    def handle_start(self):
        self.yolo.set_conveyor_active(True)
        if not self.send_cmd_with_log(
            "start_conveyor",
            self.serial.send_start_conveyor,
            "ACK_START"
        ):
            return

        self.conveyor_running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        #self.yolo.set_conveyor_active(True)

    def handle_stop(self):
        if not self.send_cmd_with_log(
            "stop_conveyor",
            self.serial.send_stop_conveyor,
            "ACK_STOP"
        ):
            return

        self.conveyor_running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.yolo.set_conveyor_active(False)

    def handle_reset(self):
        self.yolo.bolt_count = 0
        self.yolo.nut_count = 0
        self.lbl_bolt.setText("Bolt Count: 0")
        self.lbl_nut.setText("Nut Count: 0")
        self.log("[INFO] Counter reset")

    def handle_set_speed(self):
        try:
            v = int(self.speed_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid speed")
            return

        self.log(f"[CMD] SET_SPEED:{v} sent")
        ok = self.serial.send_set_speed(v)
        if not ok:
            self.log("[ERROR] No ACK_SET_SPEED")
        else:
            self.log("[ACK] ACK_SET_SPEED received")

    # ========================================================
    # SERIAL CALLBACK
    # ========================================================
    def on_serial(self, line):
        if line.startswith("RPM:"):
            self.lbl_speed.setText(f"Current Speed: {line[4:]} RPM")
        self.log(f"[STM32] {line}")

    # ========================================================
    # UI HELPERS
    # ========================================================
    @pyqtSlot(QImage)
    def update_frame(self, img):
        pix = QPixmap.fromImage(img).scaled(
            self.lbl_video.size(), Qt.KeepAspectRatio
        )
        self.lbl_video.setPixmap(pix)

    @pyqtSlot(float, float)
    def update_stats(self, fps, lat):
        self.lbl_fps.setText(f"FPS: {fps:.1f}")
        self.lbl_latency.setText(f"Latency: {lat:.1f} ms")

    @pyqtSlot(int, int)
    def update_counts(self, b, n):
        self.lbl_bolt.setText(f"Bolt Count: {b}")
        self.lbl_nut.setText(f"Nut Count: {n}")

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.txt_log.append(f"[{ts}] {msg}")

        # ---- AUTO SCROLL ----
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())


    def closeEvent(self, e):
        self.yolo.stop()
        self.yolo.wait()
        if hasattr(self, "com_timer"):
            self.com_timer.stop()
        self.serial.close()
        e.accept()


# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = ConveyorWindow(args.model, args.port, args.baud, args.mock)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
