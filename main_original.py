import cv2
import numpy as np
import json
import time
from collections import deque
from PyQt5 import QtWidgets, QtGui, QtCore

CONFIG_FILE = "focus_config.json"
DEVICE = "/dev/video0"


# ------------------ Focus Utilities ------------------ #
def laplacian_focus_metric(gray):
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def compute_weighted_focus(gray, regions):
    total, weight_sum = 0.0, 0.0
    for r in regions:
        x1, y1, x2, y2, w = r
        roi = gray[y1:y2, x1:x2]
        if roi.size == 0: continue
        score = laplacian_focus_metric(roi)
        total += score * w
        weight_sum += w
    return total / weight_sum if weight_sum else 0.0


# ------------------ GUI Class ------------------ #
class BosonFocusUtility(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FLIR Boson Focus Utility")
        self.resize(1200, 700)

        # Video and data
        self.cap = cv2.VideoCapture(1)
        self.regions = []
        self.focus_color = (0, 0, 255)
        self.edge_threshold = 100
        self.focus_history = deque(maxlen=200)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(50)  # 20 fps

        # Layout
        layout = QtWidgets.QHBoxLayout(self)
        self.video_label = QtWidgets.QLabel()
        layout.addWidget(self.video_label, 3)

        control_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(control_layout, 1)

        # Focus controls
        self.weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.weight_slider.setRange(1, 300)
        self.weight_slider.setValue(100)
        self.weight_label = QtWidgets.QLabel("Weight: 1.0")
        self.weight_slider.valueChanged.connect(self.update_weight_label)

        self.threshold_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.threshold_slider.setRange(1, 300)
        self.threshold_slider.setValue(self.edge_threshold)
        self.threshold_label = QtWidgets.QLabel(f"Edge Threshold: {self.edge_threshold}")
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)

        self.color_btn = QtWidgets.QPushButton("Change Peaking Color")
        self.color_btn.clicked.connect(self.change_color)

        self.save_btn = QtWidgets.QPushButton("💾 Save Config")
        self.save_btn.clicked.connect(self.save_config)
        self.load_btn = QtWidgets.QPushButton("📂 Load Config")
        self.load_btn.clicked.connect(self.load_config)

        # Focus trend graph
        self.graph_label = QtWidgets.QLabel()
        self.graph_label.setFixedHeight(150)
        self.graph_label.setStyleSheet("background-color: #111;")

        control_layout.addWidget(QtWidgets.QLabel("<b>Focus Controls</b>"))
        control_layout.addWidget(self.weight_label)
        control_layout.addWidget(self.weight_slider)
        control_layout.addWidget(self.threshold_label)
        control_layout.addWidget(self.threshold_slider)
        control_layout.addWidget(self.color_btn)
        control_layout.addWidget(self.save_btn)
        control_layout.addWidget(self.load_btn)
        control_layout.addSpacing(10)
        control_layout.addWidget(QtWidgets.QLabel("<b>Focus Graph</b>"))
        control_layout.addWidget(self.graph_label)
        control_layout.addStretch()

    def update_weight_label(self, value):
        self.weight_label.setText(f"Weight: {value/100:.2f}")

    def update_threshold_label(self, value):
        self.edge_threshold = value
        self.threshold_label.setText(f"Edge Threshold: {value}")

    def change_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.focus_color = (color.blue(), color.green(), color.red())

    def save_config(self):
        cfg = {
            "focus_color": self.focus_color,
            "edge_threshold": self.edge_threshold,
            "regions": [[100, 100, 200, 200, 1.0]]
        }
        json.dump(cfg, open(CONFIG_FILE, "w"), indent=2)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved config to {CONFIG_FILE}")

    def load_config(self):
        try:
            cfg = json.load(open(CONFIG_FILE))
            self.focus_color = tuple(cfg.get("focus_color", [0, 0, 255]))
            self.edge_threshold = cfg.get("edge_threshold", 100)
            self.threshold_slider.setValue(self.edge_threshold)
            QtWidgets.QMessageBox.information(self, "Loaded", f"Loaded config from {CONFIG_FILE}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))

    def update_frame(self):
        ret, frame = self.cap.read()
        if not ret: return

        frame = cv2.resize(frame, (640, 480))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        abs_lap = np.uint8(np.absolute(lap))
        _, mask = cv2.threshold(abs_lap, self.edge_threshold, 255, cv2.THRESH_BINARY)
        overlay = frame.copy()
        overlay[mask > 0] = self.focus_color
        frame = cv2.addWeighted(frame, 0.8, overlay, 0.5, 0)

        focus_score = laplacian_focus_metric(gray)
        self.focus_history.append(focus_score)

        frame = cv2.putText(frame, f"Focus: {focus_score:.1f}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Draw focus graph
        graph = np.zeros((150, 300, 3), np.uint8)
        if len(self.focus_history) > 1:
            pts = np.array([
                [int(i * 300 / len(self.focus_history)),
                 150 - int(min(v, 5000) / 5000 * 150)]
                for i, v in enumerate(self.focus_history)
            ], np.int32)
            cv2.polylines(graph, [pts], False, (0, 255, 0), 1)
        qimg_graph = QtGui.QImage(graph, 300, 150, 3 * 300, QtGui.QImage.Format_BGR888)
        self.graph_label.setPixmap(QtGui.QPixmap.fromImage(qimg_graph))

        # Convert main frame to Qt
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        qimg = QtGui.QImage(rgb_frame.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        self.video_label.setPixmap(QtGui.QPixmap.fromImage(qimg))

    def closeEvent(self, event):
        self.cap.release()
        event.accept()


# ------------------ Entry ------------------ #
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    window = BosonFocusUtility()
    window.show()
    sys.exit(app.exec_())
