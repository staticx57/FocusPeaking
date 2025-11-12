#!/usr/bin/env python3
import cv2
import numpy as np
import json
import time
import os
from collections import deque
from PyQt5 import QtWidgets, QtGui, QtCore

# ---------- Config ----------
DEVICE = "/dev/video0"
CONFIG_FILE = "focus_config.json"
FRAME_W, FRAME_H = 640, 480

# ---------- Utility functions ----------
def laplacian_focus_metric(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

# ---------- ROI-aware QLabel ----------
class VideoLabel(QtWidgets.QLabel):
    roiCreated = QtCore.pyqtSignal(tuple)   # (x1,y1,x2,y2)
    roiSelected = QtCore.pyqtSignal(int)    # region id
    roiMoved = QtCore.pyqtSignal(int, tuple)  # id, new rect
    mouseOver = QtCore.pyqtSignal(tuple)    # (x,y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._pixmap = None
        self.drawing = False
        self.start = None
        self.current_rect = None
        self.rois = []  # list of dicts {"id":int,"rect":[x1,y1,x2,y2]}
        self.selected_id = None
        self.moving = False
        self.move_offset = (0,0)

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        super().setPixmap(pixmap)
        self._pixmap = pixmap

    def map_to_frame(self, x, y):
        """Map QLabel coordinates to frame coordinates (frame is FRAME_W x FRAME_H)"""
        if self._pixmap is None:
            return 0,0
        lbl_w, lbl_h = self.width(), self.height()
        pm_w, pm_h = self._pixmap.width(), self._pixmap.height()
        # center/letterbox fit
        scale = min(lbl_w/pm_w, lbl_h/pm_h)
        disp_w, disp_h = int(pm_w*scale), int(pm_h*scale)
        x0 = (lbl_w - disp_w)//2
        y0 = (lbl_h - disp_h)//2
        if x < x0 or x > x0+disp_w or y < y0 or y > y0+disp_h:
            # outside image — clamp to nearest edge in display
            x = max(x0, min(x, x0+disp_w))
            y = max(y0, min(y, y0+disp_h))
        fx = int((x - x0) * (FRAME_W / disp_w))
        fy = int((y - y0) * (FRAME_H / disp_h))
        fx = max(0, min(FRAME_W-1, fx))
        fy = max(0, min(FRAME_H-1, fy))
        return fx, fy

    def map_from_frame(self, rect):
        """Map frame rect ([x1,y1,x2,y2]) to QLabel coordinates for drawing overlay if needed"""
        if self._pixmap is None:
            return rect
        x1,y1,x2,y2 = rect
        lbl_w, lbl_h = self.width(), self.height()
        pm_w, pm_h = self._pixmap.width(), self._pixmap.height()
        scale = min(lbl_w/pm_w, lbl_h/pm_h)
        disp_w, disp_h = int(pm_w*scale), int(pm_h*scale)
        x0 = (lbl_w - disp_w)//2
        y0 = (lbl_h - disp_h)//2
        sx = disp_w / FRAME_W
        sy = disp_h / FRAME_H
        rx1 = int(x0 + x1 * sx)
        ry1 = int(y0 + y1 * sy)
        rx2 = int(x0 + x2 * sx)
        ry2 = int(y0 + y2 * sy)
        return [rx1, ry1, rx2, ry2]

    def mousePressEvent(self, ev):
        x, y = ev.x(), ev.y()
        if ev.button() == QtCore.Qt.LeftButton:
            fx, fy = self.map_to_frame(x, y)
            # check if clicking inside existing ROI to select/move
            for r in reversed(self.rois):
                x1,y1,x2,y2 = r["rect"]
                if x1 <= fx <= x2 and y1 <= fy <= y2:
                    self.selected_id = r["id"]
                    self.roiSelected.emit(self.selected_id)
                    self.moving = True
                    # store offset from center to mouse point in frame coords
                    cx = (x1 + x2)//2
                    cy = (y1 + y2)//2
                    self.move_offset = (fx - cx, fy - cy)
                    return
            # otherwise start drawing
            self.drawing = True
            self.start = (fx, fy)
            self.current_rect = (fx, fy, fx, fy)

    def mouseMoveEvent(self, ev):
        x, y = ev.x(), ev.y()
        fx, fy = self.map_to_frame(x, y)
        self.mouseOver.emit((fx, fy))
        if self.drawing and self.start:
            x0, y0 = self.start
            self.current_rect = (x0, y0, fx, fy)
            self.update()
        elif self.moving and self.selected_id is not None:
            # move selected ROI such that its center is near current point minus offset
            idx = next((i for i,r in enumerate(self.rois) if r["id"]==self.selected_id), None)
            if idx is None:
                return
            r = self.rois[idx]
            x1,y1,x2,y2 = r["rect"]
            w = x2 - x1; h = y2 - y1
            cx = fx - self.move_offset[0]
            cy = fy - self.move_offset[1]
            nx1 = max(0, min(FRAME_W - w, cx - w//2))
            ny1 = max(0, min(FRAME_H - h, cy - h//2))
            new_rect = [int(nx1), int(ny1), int(nx1 + w), int(ny1 + h)]
            r["rect"] = new_rect
            self.roiMoved.emit(self.selected_id, tuple(new_rect))
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if self.drawing and self.current_rect is not None:
                x1,y1,x2,y2 = self.current_rect
                if abs(x2-x1) > 10 and abs(y2-y1) > 10:
                    norm_rect = [int(min(x1,x2)), int(min(y1,y2)), int(max(x1,x2)), int(max(y1,y2))]
                    self.roiCreated.emit(tuple(norm_rect))
                self.current_rect = None
                self.start = None
            if self.moving:
                self.moving = False
            self.drawing = False
            self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        # draw overlay ROIs on top of pixmap
        if self._pixmap is None:
            return
        qp = QtGui.QPainter(self)
        pen_sel = QtGui.QPen(QtGui.QColor(255, 255, 0), 2)  # selected yellow
        pen_reg = QtGui.QPen(QtGui.QColor(0, 255, 0), 1)
        brush_alpha = QtGui.QBrush(QtGui.QColor(0, 255, 0, 60))
        for r in self.rois:
            rect_disp = self.map_from_frame(r["rect"])
            pen = pen_sel if r.get("id")==self.selected_id else pen_reg
            qp.setPen(pen)
            color = QtGui.QColor(0,255,0, int(60 * r.get("weight",1.0)))
            qp.setBrush(QtGui.QBrush(color))
            x1,y1,x2,y2 = rect_disp
            qp.drawRect(x1, y1, x2-x1, y2-y1)
        if self.current_rect:
            rect_disp = self.map_from_frame([int(self.current_rect[0]),int(self.current_rect[1]),
                                            int(self.current_rect[2]),int(self.current_rect[3])])
            qp.setPen(QtGui.QPen(QtGui.QColor(0,255,255),2, QtCore.Qt.DashLine))
            qp.setBrush(QtCore.Qt.NoBrush)
            x1,y1,x2,y2 = rect_disp
            qp.drawRect(x1,y1,x2-x1,y2-y1)
        qp.end()

# ---------- Main GUI ----------
class BosonFocusGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Boson Focus GUI (ROI)")
        self.resize(1200, 700)

        # video capture
        self.cap = cv2.VideoCapture(DEVICE)
        # pre-allocate blank frame if capture fails at start
        self.frame = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)

        # state
        self.regions = []   # list of dicts: {"id":int,"rect":[x1,y1,x2,y2],"weight":float,"score":float}
        self.next_id = 1
        self.current_weight = 1.0
        self.focus_color = (0, 0, 255)  # BGR
        self.edge_threshold = 100
        self.focus_history = deque(maxlen=400)
        self.selected_id = None

        # timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)  # 20 Hz

        # layout
        main_l = QtWidgets.QHBoxLayout(self)
        left_l = QtWidgets.QVBoxLayout()
        main_l.addLayout(left_l, 3)

        # Video widget (custom)
        self.video_label = VideoLabel()
        self.video_label.setFixedSize(800, 600)
        left_l.addWidget(self.video_label)

        # right pane controls
        right_l = QtWidgets.QVBoxLayout()
        main_l.addLayout(right_l, 1)

        # weight slider for new/selected ROI
        right_l.addWidget(QtWidgets.QLabel("Selected ROI weight"))
        self.weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.weight_slider.setRange(1, 300)  # 0.01 .. 3.00
        self.weight_slider.setValue(int(self.current_weight * 100))
        self.weight_slider.valueChanged.connect(self._weight_changed)
        right_l.addWidget(self.weight_slider)
        self.weight_label = QtWidgets.QLabel("Weight: 1.00")
        right_l.addWidget(self.weight_label)

        # edge threshold
        right_l.addWidget(QtWidgets.QLabel("Edge threshold"))
        self.th_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.th_slider.setRange(1, 300)
        self.th_slider.setValue(self.edge_threshold)
        self.th_slider.valueChanged.connect(self._edge_changed)
        right_l.addWidget(self.th_slider)
        self.th_label = QtWidgets.QLabel(f"Threshold: {self.edge_threshold}")
        right_l.addWidget(self.th_label)

        # color picker
        self.color_btn = QtWidgets.QPushButton("Pick peaking color")
        self.color_btn.clicked.connect(self._pick_color)
        right_l.addWidget(self.color_btn)

        # ROI table
        right_l.addWidget(QtWidgets.QLabel("ROIs (id / weight / score)"))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["id","weight","score","actions"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.cellClicked.connect(self._table_clicked)
        right_l.addWidget(self.table, 1)

        # buttons
        btns = QtWidgets.QHBoxLayout()
        self.del_btn = QtWidgets.QPushButton("Delete ROI")
        self.del_btn.clicked.connect(self._delete_selected)
        btns.addWidget(self.del_btn)
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self._save_config)
        btns.addWidget(self.save_btn)
        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self._load_config)
        btns.addWidget(self.load_btn)
        right_l.addLayout(btns)

        # graph preview
        right_l.addWidget(QtWidgets.QLabel("Focus trend"))
        self.graph_label = QtWidgets.QLabel()
        self.graph_label.setFixedHeight(180)
        self.graph_label.setStyleSheet("background:#111;")
        right_l.addWidget(self.graph_label)

        # connect video label signals
        self.video_label.roiCreated.connect(self._on_roi_created)
        self.video_label.roiSelected.connect(self._on_roi_selected)
        self.video_label.roiMoved.connect(self._on_roi_moved)
        self.video_label.mouseOver.connect(lambda p: None)

        # load config if exists
        if os.path.exists(CONFIG_FILE):
            self._load_config()
        else:
            # create sample default
            self._create_sample_config()

    # ---------- ROI management ----------
    def _on_roi_created(self, rect):
        x1,y1,x2,y2 = rect
        r = {"id": self.next_id, "rect":[x1,y1,x2,y2], "weight": self.current_weight, "score":0.0}
        self.regions.append(r)
        self.next_id += 1
        self._sync_rois_to_label()
        self._refresh_table()

    def _on_roi_selected(self, rid):
        self.selected_id = rid
        # select row in table
        for row in range(self.table.rowCount()):
            if int(self.table.item(row,0).text()) == rid:
                self.table.selectRow(row)
        # set slider to that weight
        reg = self._find_region(rid)
        if reg:
            self.weight_slider.setValue(int(reg["weight"]*100))

    def _on_roi_moved(self, rid, rect):
        reg = self._find_region(rid)
        if reg:
            reg["rect"] = list(rect)
            self._sync_rois_to_label()
            self._refresh_table()

    def _find_region(self, rid):
        return next((r for r in self.regions if r["id"]==rid), None)

    def _delete_selected(self):
        if self.selected_id is None:
            return
        self.regions = [r for r in self.regions if r["id"] != self.selected_id]
        self.selected_id = None
        self._sync_rois_to_label()
        self._refresh_table()

    def _sync_rois_to_label(self):
        # copy simple list of rois (id + rect + weight) to video label for overlay drawing and selection
        rois_for_label = []
        for r in self.regions:
            rois_for_label.append({"id": r["id"], "rect": r["rect"], "weight": r["weight"]})
        self.video_label.rois = rois_for_label
        self.video_label.selected_id = self.selected_id
        self.video_label.update()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for r in self.regions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{r['weight']:.2f}"))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{r.get('score',0):.0f}"))
            btn = QtWidgets.QPushButton("Select")
            btn.clicked.connect(lambda _, rid=r["id"]: self._select_from_table(rid))
            self.table.setCellWidget(row, 3, btn)

    def _select_from_table(self, rid):
        self.selected_id = rid
        self._on_roi_selected(rid)
        self._sync_rois_to_label()

    def _table_clicked(self, row, col):
        if col == 0:
            rid = int(self.table.item(row,0).text())
            self._select_from_table(rid)

    # ---------- UI events ----------
    def _weight_changed(self, val):
        w = val / 100.0
        self.current_weight = w
        self.weight_label.setText(f"Weight: {w:.2f}")
        # apply to selected ROI if any
        if self.selected_id:
            r = self._find_region(self.selected_id)
            if r:
                r["weight"] = w
                self._sync_rois_to_label()
                self._refresh_table()

    def _edge_changed(self, val):
        self.edge_threshold = val
        self.th_label.setText(f"Threshold: {val}")

    def _pick_color(self):
        qcolor = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.focus_color[2], self.focus_color[1], self.focus_color[0]))
        if qcolor.isValid():
            # convert to BGR
            self.focus_color = (qcolor.blue(), qcolor.green(), qcolor.red())

    # ---------- Config I/O ----------
    def _save_config(self):
        data = {
            "focus_color": list(self.focus_color),
            "edge_threshold": self.edge_threshold,
            "regions": [{"id":r["id"], "rect":r["rect"], "weight":r["weight"]} for r in self.regions]
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved config to {CONFIG_FILE}")

    def _load_config(self):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            self.focus_color = tuple(data.get("focus_color", [0,0,255]))
            self.edge_threshold = int(data.get("edge_threshold", self.edge_threshold))
            self.th_slider.setValue(self.edge_threshold)
            self.regions = [{"id":r["id"], "rect":r["rect"], "weight":r.get("weight",1.0), "score":0.0} for r in data.get("regions",[])]
            self.next_id = max((r["id"] for r in self.regions), default=0) + 1
            self._sync_rois_to_label()
            self._refresh_table()
            QtWidgets.QMessageBox.information(self, "Loaded", f"Loaded {len(self.regions)} regions")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to load config: {e}")

    def _create_sample_config(self):
        self.focus_color = (0,0,255)
        self.regions = [
            {"id":1, "rect":[100,40,540,180], "weight":2.0, "score":0.0},
            {"id":2, "rect":[120,200,520,320], "weight":1.0, "score":0.0},
            {"id":3, "rect":[140,340,500,460], "weight":0.6, "score":0.0}
        ]
        self.next_id = 4
        self._sync_rois_to_label()
        self._refresh_table()

    # ---------- Main loop tick ----------
    def _tick(self):
        # read frame
        ret, frame = self.cap.read()
        if not ret:
            # if can't read, keep previous frame (blank)
            frame = self.frame.copy()
        else:
            frame = cv2.resize(frame, (FRAME_W, FRAME_H))
            self.frame = frame.copy()

        # process peaking overlay
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        abs_lap = np.uint8(np.absolute(lap))
        _, mask = cv2.threshold(abs_lap, self.edge_threshold, 255, cv2.THRESH_BINARY)
        overlay = frame.copy()
        overlay[mask > 0] = self.focus_color
        displayed = cv2.addWeighted(frame, 0.8, overlay, 0.6, 0)

        # compute per-region scores
        total_w = 0.0; total_score = 0.0
        for r in self.regions:
            rx1,ry1,rx2,ry2 = [int(v) for v in r["rect"]]
            rx1 = max(0,min(FRAME_W-1,rx1)); rx2 = max(1,min(FRAME_W,rx2))
            ry1 = max(0,min(FRAME_H-1,ry1)); ry2 = max(1,min(FRAME_H,ry2))
            if rx2<=rx1 or ry2<=ry1:
                r["score"] = 0.0
                continue
            roi = gray[ry1:ry2, rx1:rx2]
            s = laplacian_focus_metric(roi) if roi.size else 0.0
            r["score"] = s
            total_score += s * r["weight"]
            total_w += r["weight"]

        global_score = (total_score/total_w) if total_w>0 else 0.0
        self.focus_history.append(global_score)

        # draw region overlays and labels onto displayed frame
        for r in self.regions:
            x1,y1,x2,y2 = [int(v) for v in r["rect"]]
            color = (0,255,255) if (self.selected_id and r["id"]==self.selected_id) else (0,255,0)
            cv2.rectangle(displayed, (x1,y1), (x2,y2), color, 2)
            label = f"id={r['id']} w={r['weight']:.2f} s={r['score']:.0f}"
            cv2.putText(displayed, label, (x1+4, y1+18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        # draw global focus meter text
        cv2.putText(displayed, f"Global Focus: {global_score:.1f}", (10,30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)

        # convert to QImage and show
        rgb = cv2.cvtColor(displayed, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        self.video_label.setPixmap(QtGui.QPixmap.fromImage(qimg))

        # update rois list in VideoLabel for overlay drawing
        self._sync_rois_to_label()

        # refresh table values (update scores)
        for row in range(self.table.rowCount()):
            rid = int(self.table.item(row,0).text())
            r = self._find_region(rid)
            if r:
                self.table.item(row,2).setText(f"{r.get('score',0):.0f}")

        # update graph
        graph = np.zeros((180, 300, 3), dtype=np.uint8)
        if len(self.focus_history) > 1:
            pts = np.array([
                [int(i * 300 / max(1, len(self.focus_history)-1)),
                 180 - int(min(v, 5000) / 5000 * 180)]
                for i, v in enumerate(self.focus_history)
            ], np.int32)
            cv2.polylines(graph, [pts], False, (0,255,0), 1)
        # border and label
        cv2.rectangle(graph, (0,0),(299,179), (255,255,255), 1)
        cv2.putText(graph, "Focus Trend", (6,14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255),1)
        qg = QtGui.QImage(graph.data, graph.shape[1], graph.shape[0], graph.shape[1]*3, QtGui.QImage.Format_BGR888)
        self.graph_label.setPixmap(QtGui.QPixmap.fromImage(qg))

    # ---------- Closing ----------
    def closeEvent(self, ev):
        try:
            self.cap.release()
        except:
            pass
        ev.accept()

# ---------- Run ----------
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    gui = BosonFocusGUI()
    gui.show()
    sys.exit(app.exec_())
