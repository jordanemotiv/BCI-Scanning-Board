### ---------------------------------------------------------------------------------- ###
# FINAL VERSION: Single-Switch Scanning Board (Diagnostics Mode)
# Author: Jordan Labio
# Date: 2026-07-21
# Description: This is the final version of the BCI Scanning Board that operates in a "Diagnostics Mode" for real-time testing and debugging of Emotiv Cortex.
#              It includes a setup screen, configuration options, and a live headset trace for monitoring mental commands, contact quality, and EEG quality.
#              It is intended to help nonverbal individuals communicate more effectively using thought and facial expressions. It is user-friendly and provides visual 
#              feedback for both the user and the caregiver.
#               
#               2026-07-18
                # - Reverted UI to native vector design, removing external image dependencies.
                # - Updated color palette, typography, and canvas treatments to align with official EMOTIV brand specifications (#2ecc71 green, #d9145a magenta, slate backdrops).
                # - Restored standard operating system window controls and top navigation tabs for Contact Quality and EEG Quality.

                # 2026-07-19
                # - Integrated Cortex API "fac" WebSocket data stream alongside "com", "dev", and "eq" pipelines.
                # - Mapped teeth clench ("clench") to Select and brow move to Change Speed as backup inputs.
                # - Implemented independent facial latch state tracking to prevent 32Hz telemetry spam.
                # - Added bottom selector checkbox "Include Facial Expressions" to toggle muscle input pipeline on or off.
                # - Dynamic layout updates for controls instruction text based on facial selector status.

                # 2026-07-20
                # - Expanded top state tracker telemetry box to show live dual-stream status (Mental Intent and Facial EMG State).
                # - Separated input threshold variables: Mental Threshold set to 0.35 and Facial Threshold set to 0.70.
                # - Implemented dual-phase scanner cooldown pause (2.5s) on both row locking and column selection to prevent double-triggers.
                # - Added independent "Include Thoughts" checkbox alongside "Include Facial Expressions" for granular pipeline control.

                # 2026-07-21
                # - Resolved EMOTIV API facial expression bug by adding string alias mapping for "frown" in addition to "furrow".
                # - Integrated interactive hardware sensitivity tuning panel with real-time sliders for Thought Sensitivity (0.05 - 0.95) and Facial Sensitivity (0.05 - 0.95).
                # - Refined board highlight states with EMOTIV hot-pink palette for active row scans and target intersection locks.

                # 2026-07-22
                # - Added asynchronous offline Text-to-Speech (TTS) engine integration via pyttsx3, connected to a dedicated SPEAK button and grid tile.
                # - Added BACKSPACE control button and grid tile for single-character deletion.
                # - Added PAUSE / RESUME scanner control button, grid tile, and hotkey (P) for user breaks.
                # - Added Cooldown Duration slider (0.5s - 5.0s) to the hardware tuning panel.
                # - Replaced telemetry bar text during cooldowns with a prominent visual countdown alert.
                # - Added EXIT APP button and implemented closeEvent hard process termination (os._exit(0)) to cleanly stop background WebSocket threads and immediately release the terminal. 
### ---------------------------------------------------------------------------------- ###

import sys
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, 
                             QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QStackedWidget, QCheckBox, QSlider)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

# --- GRID LAYOUT MATRICES ---
BOARD_1_PHRASES = [
    ["I HAVE TO TELL YOU SOMETHING", "I LOVE YOU", "YES", "NO", "THANK YOU", "YOU'RE WELCOME", "HELLO"],
    ["I AM", "HAPPY", "SAD", "TIRED", "HOT", "COLD", "EXCITED"],
    ["I HAVE A PROBLEM", "PAIN", "CRAMP", "ITCH", "STOP", "SICK", "UNCOMFORTABLE"],
    ["I NEED", "SUCTION", "MEDICINE", "BATHE", "BATHROOM", "BED", "BREATHING MACHINE"],
    ["MASSAGE", "LEG", "ARM", "HIPS", "HEAD", "LEFT", "RIGHT"],
    ["I WANT", "FOOD", "DRINK", "TV", "PHONE", "COMPUTER", "HELP"],
    ["TO GO", "TO CALL", "A HUG", "A KISS", "COMPANY", "FLIP OVER", "SOMETHING ELSE"]
]

BOARD_2_ALPHA = [
    ["A", "B", "C", "D", "YES", "NO"],
    ["E", "F", "G", "H", "MAYBE", "I DON'T KNOW"],
    ["I", "J", "K", "L", "M", "N"],
    ["O", "P", "QU", "R", "S", "T"],
    ["U", "V", "W", "X", "Y", "Z"],
    ["1", "2", "3", "4", "5", "6"],
    ["7", "8", "9", "0", "THANK YOU", "SOMETHING ELSE"],
    ["BACKSPACE", "SPEAK", "SPACE", "PAUSE SCANNER", "CLEAR MESSAGE", "FLIP OVER"]
]


# --- ASYNCHRONOUS OFFLINE TTS THREAD ---
class TTSThread(QThread):
    """Worker thread for Speech Synthesis so audio processing never blocks GUI loops."""
    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(self.text)
            engine.runAndWait()
        except Exception as e:
            print(f"[TTS Exception] {e}")


# --- BACKGROUND MULTI-STREAM CORTEX THREAD WORKER ---
class EmotivCortexWorker(QThread):
    mental_command_signal = pyqtSignal(str, float)
    contact_quality_signal = pyqtSignal(dict)  
    eeg_quality_signal = pyqtSignal(dict)      
    facial_expression_signal = pyqtSignal(str, float, str, float)
    device_name_signal = pyqtSignal(str)       
    status_signal = pyqtSignal(str)

    def run(self):
        self.status_signal.emit("Connecting to Cortex Service...")
        
        client_id = ""
        client_secret = ""
        profile_name = ""
        
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                    client_id = config.get("cortex_client_id", config.get("client_id", ""))
                    client_secret = config.get("cortex_client_secret", config.get("client_secret", ""))
                    profile_name = config.get("profile_name", "")
            except Exception as e:
                self.status_signal.emit(f"Error loading config.json: {e}")

        if not client_id or not client_secret:
            self.status_signal.emit("API Credentials Missing in config.json.")
            return

        try:
            from cortex import Cortex
        except ImportError:
            self.status_signal.emit("Could not find 'cortex.py' file.")
            return

        try:
            cortex = Cortex(client_id, client_secret)

            orig_on_message = cortex.on_message
            
            def patched_on_message(ws, message):
                try:
                    msg = json.loads(message)
                    if isinstance(msg, dict):
                        
                        if "dev" in msg:
                            raw_dev = msg["dev"]
                            if isinstance(raw_dev, list):
                                nested_list = None
                                for item in raw_dev:
                                    if isinstance(item, list):
                                        nested_list = item
                                        break
                                
                                if nested_list and len(nested_list) >= 5:
                                    numbers = nested_list
                                else:
                                    idx = 2 if len(raw_dev) == 8 else 0
                                    numbers = raw_dev[idx:]

                                if len(numbers) >= 5:
                                    self.contact_quality_signal.emit({
                                        "AF3": int(numbers[0]),
                                        "T7":  int(numbers[1]),
                                        "Pz":  int(numbers[2]),
                                        "T8":  int(numbers[3]),
                                        "AF4": int(numbers[4])
                                    })
                                    self.status_signal.emit("Live Stream Active. Monitoring Diagnostics...")
                        
                        if "eq" in msg:
                            raw_eq = msg["eq"]
                            if isinstance(raw_eq, list) and len(raw_eq) >= 5:
                                eq_idx = 3 if len(raw_eq) == 8 else 0
                                numbers = raw_eq[eq_idx:]
                                if len(numbers) >= 5:
                                    self.eeg_quality_signal.emit({
                                        "AF3": int(numbers[0]),
                                        "T7":  int(numbers[1]),
                                        "Pz":  int(numbers[2]),
                                        "T8":  int(numbers[3]),
                                        "AF4": int(numbers[4])
                                    })
                                    self.status_signal.emit("Live Stream Active. Monitoring Diagnostics...")
                                    
                        if "fac" in msg:
                            raw_fac = msg["fac"]
                            if isinstance(raw_fac, list) and len(raw_fac) >= 5:
                                u_act = str(raw_fac[1])
                                u_pow = float(raw_fac[2])
                                l_act = str(raw_fac[3])
                                l_pow = float(raw_fac[4])
                                self.facial_expression_signal.emit(u_act, u_pow, l_act, l_pow)
                                
                except Exception as e:
                    pass
                
                return orig_on_message(ws, message)

            cortex.on_message = patched_on_message

            def handle_data_packet(*args, **kwargs):
                data = kwargs.get("data", args[0] if args else {})
                if isinstance(data, dict) and "action" in data and "power" in data:
                    self.mental_command_signal.emit(str(data["action"]), float(data["power"]))
                elif isinstance(data, dict) and "com" in data:
                    self.mental_command_signal.emit(str(data["com"][0]), float(data["com"][1]))

            def session_done_callback(*args, **kwargs):
                if hasattr(cortex, "headset_id") and cortex.headset_id:
                    self.device_name_signal.emit(str(cortex.headset_id))
                else:
                    self.device_name_signal.emit("INSIGHT HEADSET")

                if profile_name:
                    self.status_signal.emit(f"Loading Profile: {profile_name}...")
                    if hasattr(cortex, "setup_profile"):
                        cortex.setup_profile(profile_name, "load")
                    elif hasattr(cortex, "load_profile"):
                        cortex.load_profile(profile_name)
                
                for method_name in ["subscribe", "sub_request", "request_sub", "send_subscribe"]:
                    if hasattr(cortex, method_name):
                        getattr(cortex, method_name)(["com", "dev", "eq", "fac"])
                        break

            cortex.bind(create_session_done=session_done_callback)
            cortex.bind(new_com_data=handle_data_packet)
            
            self.status_signal.emit("Cortex Linked. Waiting for Device Packets...")
            cortex.open()
            
        except Exception as e:
            self.status_signal.emit(f"Cortex Connection Failed: {e}")


# --- VISUAL HEADSET MAP CANVAS WIDGET ---
class HeadsetMapWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(360, 360)
        self.cq_status = {"AF3": 0, "AF4": 0, "T7": 0, "T8": 0, "Pz": 0}
        self.eq_status = {"AF3": 0, "AF4": 0, "T7": 0, "T8": 0, "Pz": 0}
        self.display_mode = "CQ" 
        
        self.sensor_positions = {
            "AF3": (120, 75),   
            "AF4": (240, 75),   
            "T7":  (50, 165),   
            "T8":  (310, 165),  
            "Pz":  (180, 285)   
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor("#eef2f7"))
        painter.setPen(QPen(QColor("#cbd5e1"), 2))
        painter.drawEllipse(40, 40, 280, 280)
        
        painter.setBrush(QColor("#cbd5e1"))
        painter.drawPolygon([QPoint(165, 40), QPoint(195, 40), QPoint(180, 15)])

        active_dataset = self.cq_status if self.display_mode == "CQ" else self.eq_status

        for sensor, (x, y) in self.sensor_positions.items():
            val = active_dataset.get(sensor, 0)
            
            if val >= 3:
                node_color = QColor("#2ecc71")     
                border_color = QColor("#27ae60")
            elif val > 0:
                node_color = QColor("#f39c12")    
                border_color = QColor("#d35400")
            else:
                node_color = QColor("#1e1e24")    
                border_color = QColor("#334155")

            painter.setBrush(node_color)
            painter.setPen(QPen(border_color, 2))
            painter.drawEllipse(x - 16, y - 16, 32, 32)

            painter.setPen(QPen(QColor("#ffffff") if val == 0 else QColor("#111111")))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(x - 13, y + 4, sensor)


# --- MAIN WIZARD INTERFACE ---
class BCICommunicationBoard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EMOTIV BCI Assistive Communication System")
        
        self.page_container = QStackedWidget()
        self.setCentralWidget(self.page_container)
        
        self.current_setup_tab = "CQ"
        self.build_preflight_screen()
        self.build_keyboard_screen()
        
        self.page_container.addWidget(self.setup_page)
        self.page_container.addWidget(self.keyboard_page)
        self.page_container.setCurrentIndex(0) 

        self.cortex_thread = EmotivCortexWorker()
        self.cortex_thread.status_signal.connect(self.display_network_logs)
        self.cortex_thread.device_name_signal.connect(self.update_hardware_banner)
        self.cortex_thread.contact_quality_signal.connect(self.process_contact_quality)
        self.cortex_thread.eeg_quality_signal.connect(self.process_eeg_quality)
        self.cortex_thread.mental_command_signal.connect(self.route_bci_command)
        self.cortex_thread.facial_expression_signal.connect(self.route_facial_command)
        self.cortex_thread.start()

    def build_preflight_screen(self):
        self.setup_page = QWidget()
        self.setup_page.setStyleSheet("background-color: #ffffff;")
        layout = QVBoxLayout(self.setup_page)
        layout.setContentsMargins(40, 40, 40, 40)

        nav_header = QHBoxLayout()
        
        self.cq_tab_btn = QPushButton("Contact Quality")
        self.cq_tab_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.cq_tab_btn.setFlat(True)
        self.cq_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cq_tab_btn.clicked.connect(lambda: self.switch_setup_tab("CQ"))
        nav_header.addWidget(self.cq_tab_btn)
        
        self.eq_tab_btn = QPushButton("EEG Quality")
        self.eq_tab_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        self.eq_tab_btn.setFlat(True)
        self.eq_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eq_tab_btn.clicked.connect(lambda: self.switch_setup_tab("EQ"))
        nav_header.addWidget(self.eq_tab_btn)
        
        nav_header.addStretch()
        layout.addLayout(nav_header)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(40)
        
        left_column_layout = QVBoxLayout()
        
        self.device_name_label = QLabel("DEVICE: CONNECTING...")
        self.device_name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.device_name_label.setStyleSheet("color: #4f5d75; background-color: #f8f9fa; padding: 8px; border-radius: 6px; border: 1px solid #e2e8f0; margin-bottom: 5px;")
        self.device_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_name_label.setFixedHeight(40)  
        left_column_layout.addWidget(self.device_name_label)

        self.head_map = HeadsetMapWidget()
        left_column_layout.addWidget(self.head_map, alignment=Qt.AlignmentFlag.AlignCenter)
        body_layout.addLayout(left_column_layout)

        text_layout = QVBoxLayout()
        self.instructions_title = QLabel("")
        self.instructions_title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.instructions_title.setStyleSheet("color: #1a1a1a;")
        text_layout.addWidget(self.instructions_title)

        self.instructions_body = QLabel("")
        self.instructions_body.setFont(QFont("Segoe UI", 11))
        self.instructions_body.setWordWrap(True)
        self.instructions_body.setStyleSheet("color: #4a5568; line-height: 150%;")
        text_layout.addWidget(self.instructions_body)
        text_layout.addStretch()
        
        self.completion_percentage_label = QLabel("0%")
        self.completion_percentage_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.completion_percentage_label.setStyleSheet("color: #cbd5e1;")
        text_layout.addWidget(self.completion_percentage_label)

        body_layout.addLayout(text_layout)
        layout.addLayout(body_layout, stretch=1)

        footer_layout = QHBoxLayout()
        self.setup_network_log = QLabel("BCI: Waiting for connection payload sequence...")
        self.setup_network_log.setFont(QFont("Segoe UI", 10))
        footer_layout.addWidget(self.setup_network_log)
        footer_layout.addStretch()

        self.continue_btn = QPushButton("Continue >")
        self.continue_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.continue_btn.setFixedSize(140, 42)
        self.continue_btn.setEnabled(False) 
        self.continue_btn.setStyleSheet("""
            QPushButton:enabled { background-color: #d9145a; color: white; border-radius: 4px; }
            QPushButton:disabled { background-color: #e2e8f0; color: #94a3b8; border-radius: 4px; }
        """)
        self.continue_btn.clicked.connect(self.transition_to_keyboard)
        footer_layout.addWidget(self.continue_btn)
        layout.addLayout(footer_layout)

        self.switch_setup_tab("CQ")

    def build_keyboard_screen(self):
        self.keyboard_page = QWidget()
        self.keyboard_page.setStyleSheet("background-color: #f8fafc;") 
        self.main_layout = QVBoxLayout(self.keyboard_page)
        
        self.boards = {"ALPHA": BOARD_2_ALPHA, "PHRASES": BOARD_1_PHRASES}
        self.current_board_name = "ALPHA"
        self.current_matrix = self.boards[self.current_board_name]
        
        self.SCAN_ROWS = 0
        self.SCAN_COLS = 1
        self.scanning_state = self.SCAN_ROWS
        
        self.active_row = 0
        self.active_col = 0
        
        self.scan_intervals = [2000, 1500, 1000, 600] 
        self.speed_names = ["SLOW", "MEDIUM", "FAST", "VERY FAST"]
        self.speed_index = 1 
        self.composed_text = ""

        # --- THRESHOLDS, COOLDOWN, & PAUSE STATES ---
        self.MENTAL_THRESHOLD = 0.35      
        self.FACIAL_THRESHOLD = 0.70      
        self.SELECTION_COOLDOWN_MS = 2500 
        
        self.latch_released = True
        self.facial_latch_released = True 
        self.in_cooldown = False          
        self.is_paused = False            
        
        self.cooldown_remaining_ms = 0
        self.cooldown_phase_label = ""

        self.mental_state_str = "NEUTRAL (IDLING) [Power: 0.00]"
        self.facial_state_str = "READY (IDLING)"

        # =========================================================================
        # 💬 COMPOSED MESSAGE & QUICK-ACTION CONTROL BAY
        # =========================================================================
        # 1. Instantiate layout container first
        message_bar_layout = QHBoxLayout()

        # 2. Display box
        self.display_box = QLabel("Composed Message: ")
        self.display_box.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.display_box.setStyleSheet("background-color: #1e1e24; color: #2ecc71; padding: 15px; border-radius: 8px; border: 2px solid #111115;")
        self.display_box.setWordWrap(True)
        message_bar_layout.addWidget(self.display_box, stretch=1)

        # 3. Quick Control Sidebar Buttons
        action_btn_layout = QVBoxLayout()
        action_btn_layout.setSpacing(6)

        self.speak_btn = QPushButton("🔊 SPEAK")
        self.speak_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.speak_btn.setFixedSize(130, 36)
        self.speak_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speak_btn.setStyleSheet("QPushButton { background-color: #d9145a; color: white; border-radius: 6px; } QPushButton:hover { background-color: #b00f46; }")
        self.speak_btn.clicked.connect(self.speak_message)
        action_btn_layout.addWidget(self.speak_btn)

        self.backspace_btn = QPushButton("⌫ BACKSPACE")
        self.backspace_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.backspace_btn.setFixedSize(130, 30)
        self.backspace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backspace_btn.setStyleSheet("QPushButton { background-color: #4f5d75; color: white; border-radius: 6px; } QPushButton:hover { background-color: #3b4758; }")
        self.backspace_btn.clicked.connect(lambda: self.process_selection("BACKSPACE"))
        action_btn_layout.addWidget(self.backspace_btn)

        self.pause_btn = QPushButton("⏸️ PAUSE")
        self.pause_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.pause_btn.setFixedSize(130, 30)
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setStyleSheet("QPushButton { background-color: #f39c12; color: white; border-radius: 6px; } QPushButton:hover { background-color: #d35400; }")
        self.pause_btn.clicked.connect(lambda: self.process_selection("PAUSE SCANNER"))
        action_btn_layout.addWidget(self.pause_btn)

        self.exit_app_btn = QPushButton("✕ EXIT APP")
        self.exit_app_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.exit_app_btn.setFixedSize(130, 30)
        self.exit_app_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_app_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; border-radius: 6px; } QPushButton:hover { background-color: #c0392b; }")
        self.exit_app_btn.clicked.connect(self.close)
        action_btn_layout.addWidget(self.exit_app_btn)

        # 4. Attach action bar into message layout, then attach to main layout
        message_bar_layout.addLayout(action_btn_layout)
        self.main_layout.addLayout(message_bar_layout)
        # =========================================================================

        # Dynamic Unified Telemetry Box
        self.telemetry_label = QLabel()
        self.telemetry_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.main_layout.addWidget(self.telemetry_label)

        # --- HARDWARE SENSITIVITY & TIMING TUNING BAR ---
        tuning_panel = QWidget()
        tuning_panel.setStyleSheet("background-color: #ffffff; border-radius: 6px; border: 1px solid #e2e8f0;")
        tuning_layout = QHBoxLayout(tuning_panel)
        tuning_layout.setContentsMargins(15, 6, 15, 6)

        # 1. Thought Sensitivity Slider
        self.mental_slider_lbl = QLabel(f"Thought Sens: {self.MENTAL_THRESHOLD:.2f}")
        self.mental_slider_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.mental_slider_lbl.setStyleSheet("color: #4f5d75; border: none;")
        tuning_layout.addWidget(self.mental_slider_lbl)

        self.mental_slider = QSlider(Qt.Orientation.Horizontal)
        self.mental_slider.setRange(5, 95)
        self.mental_slider.setValue(int(self.MENTAL_THRESHOLD * 100))
        self.mental_slider.setFixedWidth(110)
        self.mental_slider.setStyleSheet("QSlider::handle:horizontal { background-color: #d9145a; border-radius: 5px; }")
        self.mental_slider.valueChanged.connect(self.handle_mental_slider_changed)
        tuning_layout.addWidget(self.mental_slider)

        tuning_layout.addSpacing(20)

        # 2. Facial Sensitivity Slider
        self.facial_slider_lbl = QLabel(f"Facial Sens: {self.FACIAL_THRESHOLD:.2f}")
        self.facial_slider_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.facial_slider_lbl.setStyleSheet("color: #4f5d75; border: none;")
        tuning_layout.addWidget(self.facial_slider_lbl)

        self.facial_slider = QSlider(Qt.Orientation.Horizontal)
        self.facial_slider.setRange(5, 95)
        self.facial_slider.setValue(int(self.FACIAL_THRESHOLD * 100))
        self.facial_slider.setFixedWidth(110)
        self.facial_slider.setStyleSheet("QSlider::handle:horizontal { background-color: #d9145a; border-radius: 5px; }")
        self.facial_slider.valueChanged.connect(self.handle_facial_slider_changed)
        tuning_layout.addWidget(self.facial_slider)

        tuning_layout.addSpacing(20)

        # 3. Cooldown Duration Slider
        self.cooldown_slider_lbl = QLabel(f"Cooldown: {self.SELECTION_COOLDOWN_MS/1000:.1f}s")
        self.cooldown_slider_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.cooldown_slider_lbl.setStyleSheet("color: #4f5d75; border: none;")
        tuning_layout.addWidget(self.cooldown_slider_lbl)

        self.cooldown_slider = QSlider(Qt.Orientation.Horizontal)
        self.cooldown_slider.setRange(5, 50) 
        self.cooldown_slider.setValue(int(self.SELECTION_COOLDOWN_MS / 100))
        self.cooldown_slider.setFixedWidth(110)
        self.cooldown_slider.setStyleSheet("QSlider::handle:horizontal { background-color: #d9145a; border-radius: 5px; }")
        self.cooldown_slider.valueChanged.connect(self.handle_cooldown_slider_changed)
        tuning_layout.addWidget(self.cooldown_slider)
        
        tuning_layout.addStretch()
        self.main_layout.addWidget(tuning_panel)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.main_layout.addWidget(self.grid_container, stretch=1)
        
        self.build_board_grid()
        
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Mode: AUTOMATIC SCAN")
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #1e293b; padding-right: 10px;")
        status_layout.addWidget(self.status_label)
        
        speed_title = QLabel("Speed: ")
        speed_title.setFont(QFont("Segoe UI", 11))
        status_layout.addWidget(speed_title)
        
        self.speed_widgets = []
        for name in self.speed_names:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lbl.setFixedSize(85, 22)
            status_layout.addWidget(lbl)
            self.speed_widgets.append(lbl)
            
        status_layout.addStretch()

        self.mental_selector = QCheckBox("Include Thoughts")
        self.mental_selector.setChecked(True)
        self.mental_selector.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.mental_selector.setStyleSheet("QCheckBox { color: #334155; spacing: 4px; padding-right: 10px; }")
        self.mental_selector.toggled.connect(self.handle_stream_selectors_toggled)
        status_layout.addWidget(self.mental_selector)

        self.facial_selector = QCheckBox("Include Facial Expressions")
        self.facial_selector.setChecked(True) 
        self.facial_selector.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.facial_selector.setStyleSheet("QCheckBox { color: #334155; spacing: 4px; padding-right: 15px; }")
        self.facial_selector.toggled.connect(self.handle_stream_selectors_toggled)
        status_layout.addWidget(self.facial_selector)

        self.keyboard_network_status_label = QLabel("BCI: Calibration Completed.")
        self.keyboard_network_status_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.keyboard_network_status_label.setStyleSheet("color: #2ecc71; padding-right: 10px;")
        status_layout.addWidget(self.keyboard_network_status_label)
        
        self.controls_label = QLabel("Push/Clench = SELECT  •  Pull/Furrow = SPEED")
        self.controls_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.controls_label.setStyleSheet("color: #4f5d75; padding: 5px;")
        status_layout.addWidget(self.controls_label)
        self.main_layout.addLayout(status_layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_scanner)

        self.cooldown_ticker = QTimer(self)
        self.cooldown_ticker.timeout.connect(self.tick_cooldown_countdown)

        self.update_telemetry_box("neutral")

    def handle_mental_slider_changed(self, value):
        self.MENTAL_THRESHOLD = value / 100.0
        self.mental_slider_lbl.setText(f"Thought Sens: {self.MENTAL_THRESHOLD:.2f}")
        self.update_telemetry_box("neutral")

    def handle_facial_slider_changed(self, value):
        self.FACIAL_THRESHOLD = value / 100.0
        self.facial_slider_lbl.setText(f"Facial Sens: {self.FACIAL_THRESHOLD:.2f}")
        self.update_telemetry_box("neutral")

    def handle_cooldown_slider_changed(self, value):
        self.SELECTION_COOLDOWN_MS = value * 100
        self.cooldown_slider_lbl.setText(f"Cooldown: {self.SELECTION_COOLDOWN_MS/1000:.1f}s")

    def update_telemetry_box(self, style_preset="neutral"):
        # Guard: If system is currently on cooldown, keep the prominent countdown bar visible
        if self.in_cooldown:
            return

        mental_part = self.mental_state_str if self.mental_selector.isChecked() else "DISABLED"
        text = f"BCI FRAMEWORK — MENTAL INTENT: {mental_part}"
        
        if self.facial_selector.isChecked():
            text += f"   |   FACIAL EMG STATE: {self.facial_state_str}"
        else:
            text += f"   |   FACIAL EMG STATE: DISABLED"
        
        self.telemetry_label.setText(text)
        
        if style_preset == "neutral":
            self.telemetry_label.setStyleSheet("background-color: #1e1e24; color: #edf2f4; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #334155;")
        elif style_preset == "warning":
            self.telemetry_label.setStyleSheet("background-color: #f39c12; color: #ffffff; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #d35400;")
        elif style_preset == "locked":
            self.telemetry_label.setStyleSheet("background-color: #334155; color: #cbd5e1; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #475569;")
        elif style_preset == "mental_trigger":
            self.telemetry_label.setStyleSheet("background-color: #d9145a; color: #ffffff; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #b00f46;")
        elif style_preset == "facial_trigger":
            self.telemetry_label.setStyleSheet("background-color: #4f5d75; color: #ffffff; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #2b2d42;")

    def handle_stream_selectors_toggled(self):
        m_on = self.mental_selector.isChecked()
        f_on = self.facial_selector.isChecked()

        if m_on and f_on:
            self.controls_label.setText("Push/Clench = SELECT  •  Pull/Furrow = SPEED")
        elif m_on and not f_on:
            self.controls_label.setText("Push = SELECT  •  Pull = SPEED")
        elif not m_on and f_on:
            self.controls_label.setText("Clench = SELECT  •  Furrow = SPEED")
        else:
            self.controls_label.setText("ALL BCI OVERRIDES DISABLED")
            
        self.update_telemetry_box("neutral")

    def build_board_grid(self):
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self.grid_widgets = []
        for r in range(len(self.current_matrix)):
            row_widgets = []
            for c in range(len(self.current_matrix[r])):
                text = self.current_matrix[r][c]
                label = QLabel(text)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                label.setWordWrap(True)
                label.setStyleSheet("border: 1px solid #e2e8f0; background-color: #ffffff; border-radius: 6px; padding: 5px; color: #1e293b;")
                self.grid_layout.addWidget(label, r, c)
                row_widgets.append(label)
            self.grid_widgets.append(row_widgets)

    def switch_setup_tab(self, mode):
        self.current_setup_tab = mode
        self.head_map.display_mode = mode
        self.head_map.update()
        
        if mode == "CQ":
            self.cq_tab_btn.setStyleSheet("background: transparent; color: #d9145a; border-bottom: 3px solid #d9145a; padding-bottom: 3px; font-weight: bold;")
            self.eq_tab_btn.setStyleSheet("background: transparent; color: #94a3b8; border-bottom: 3px solid transparent; padding-bottom: 3px; font-weight: normal;")
            self.instructions_title.setText("How to ensure good Contact Quality?")
            self.instructions_body.setText(
                "Work each sensor underneath hair to make contact with the scalp. "
                "If all sensors are black, first adjust the reference sensors (the two pointy cones "
                "on the arm behind the left ear) until they are green, and then adjust the other sensors."
            )
        else:
            self.eq_tab_btn.setStyleSheet("background: transparent; color: #d9145a; border-bottom: 3px solid #d9145a; padding-bottom: 3px; font-weight: bold;")
            self.cq_tab_btn.setStyleSheet("background: transparent; color: #94a3b8; border-bottom: 3px solid transparent; padding-bottom: 3px; font-weight: normal;")
            self.instructions_title.setText("How to ensure stable EEG Quality?")
            self.instructions_body.setText(
                "EEG Quality tracks electrical noise and data saturation. Keep your facial muscles relaxed, "
                "minimize jaw clenching, and try to limit sudden movements.\n\n"
                "• Black nodes indicate heavy ambient signal noise or sensor saturation.\n"
                "• Orange nodes indicate moderate line-noise artifact interference.\n"
                "• Green nodes mean clean, pristine brainwave signals are flowing successfully."
            )
        self.update_preflight_metrics()

    def process_contact_quality(self, cq_map):
        self.head_map.cq_status.update(cq_map)
        self.head_map.update()
        self.update_preflight_metrics()

    def process_eeg_quality(self, eq_map):
        self.head_map.eq_status.update(eq_map)
        self.head_map.update()
        self.update_preflight_metrics()

    def update_preflight_metrics(self):
        stable_cq = sum(1 for val in self.head_map.cq_status.values() if val >= 3)
        stable_eq = sum(1 for val in self.head_map.eq_status.values() if val >= 3)
        total = len(self.head_map.cq_status)
        
        cq_pct = int((stable_cq / total) * 100)
        eq_pct = int((stable_eq / total) * 100)
        
        if self.current_setup_tab == "CQ":
            self.completion_percentage_label.setText(f"{cq_pct}%")
        else:
            self.completion_percentage_label.setText(f"{eq_pct}%")
            
        if cq_pct == 100 and eq_pct == 100:
            self.completion_percentage_label.setStyleSheet("color: #2ecc71;")
            self.continue_btn.setEnabled(True)
        else:
            self.completion_percentage_label.setStyleSheet("color: #cbd5e1;")
            self.continue_btn.setEnabled(False)

    def update_hardware_banner(self, device_id):
        self.device_name_label.setText(f"DEVICE: {device_id.upper()}")
        self.device_name_label.setStyleSheet("color: #2ecc71; background-color: #f8f9fa; padding: 8px; border-radius: 6px; border: 1px solid #2ecc71; font-weight: bold;")

    def transition_to_keyboard(self):
        self.page_container.setCurrentIndex(1)
        self.timer.start(self.scan_intervals[self.speed_index])
        self.update_ui_highlights()
        self.update_status_bar()

    def display_network_logs(self, text):
        self.setup_network_log.setText(f"BCI: {text}")
        if "Active" in text or "Monitoring" in text:
            self.setup_network_log.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif "Failed" in text or "Missing" in text:
            self.setup_network_log.setStyleSheet("color: #d9145a; font-weight: bold;")
        else:
            self.setup_network_log.setStyleSheet("color: #f39c12; font-weight: bold;")

    def route_bci_command(self, command, power):
        if self.page_container.currentIndex() != 1 or self.in_cooldown or self.is_paused:
            return

        if not self.mental_selector.isChecked():
            return

        clean_command = command.strip().lower()
        action_map = {"push": "SELECT", "pull": "CHANGE SPEED", "neutral": "IDLE"}
        mapped_action = action_map.get(clean_command, "UNKNOWN")

        if clean_command == "neutral":
            self.mental_state_str = f"NEUTRAL (IDLING) [Power: {power:.2f}]"
            self.update_telemetry_box("neutral")
            self.latch_released = True
            return

        if power < self.MENTAL_THRESHOLD:
            self.mental_state_str = f"{clean_command.upper()} ({mapped_action}) [Power: {power:.2f}] (Below Threshold)"
            self.update_telemetry_box("warning")
            self.latch_released = True
            return

        if not self.latch_released:
            self.mental_state_str = f"{clean_command.upper()} ({mapped_action}) [Power: {power:.2f}] (LOCKED)"
            self.update_telemetry_box("locked")
            return

        self.mental_state_str = f"TRIGGERED {clean_command.upper()}! [Power: {power:.2f}]"
        self.update_telemetry_box("mental_trigger")
        self.latch_released = False
        
        if clean_command == "push":
            self.trigger_select_event()
        elif clean_command == "pull":
            self.trigger_speed_change()

    def route_facial_command(self, u_act, u_pow, l_act, l_pow):
        if self.page_container.currentIndex() != 1 or self.in_cooldown or self.is_paused:
            return

        if not self.facial_selector.isChecked():
            return

        clench_active = (l_act.strip().lower() == "clench" and l_pow >= self.FACIAL_THRESHOLD)
        furrow_active = (u_act.strip().lower() in ["frown", "furrow"] and u_pow >= self.FACIAL_THRESHOLD)

        if not clench_active and not furrow_active:
            self.facial_latch_released = True
            if self.facial_state_str != "READY (IDLING)":
                self.facial_state_str = "READY (IDLING)"
                self.update_telemetry_box("neutral")
            return

        if not self.facial_latch_released:
            return

        if clench_active:
            self.facial_state_str = f"TRIGGERED CLENCH (SELECT BACKUP)! [Power: {l_pow:.2f}]"
            self.update_telemetry_box("facial_trigger")
            self.facial_latch_released = False
            self.trigger_select_event()
            
        elif furrow_active:
            self.facial_state_str = f"TRIGGERED FURROW (SPEED BACKUP)! [Power: {u_pow:.2f}]"
            self.update_telemetry_box("facial_trigger")
            self.facial_latch_released = False
            self.trigger_speed_change()

    def advance_scanner(self):
        if self.is_paused: return
        if self.scanning_state == self.SCAN_ROWS:
            self.active_row = (self.active_row + 1) % len(self.current_matrix)
        elif self.scanning_state == self.SCAN_COLS:
            self.active_col = (self.active_col + 1) % len(self.current_matrix[self.active_row])
        self.update_ui_highlights()

    def update_ui_highlights(self):
        for r in range(len(self.grid_widgets)):
            for c in range(len(self.grid_widgets[r])):
                widget = self.grid_widgets[r][c]
                if not widget: continue
                
                text = widget.text()
                is_flip_button = (text == "FLIP OVER")
                is_starter_col = (self.current_board_name == "PHRASES" and c == 0)
                is_special_action = (text in ["BACKSPACE", "SPEAK", "PAUSE SCANNER", "CLEAR MESSAGE"])
                
                base_style = "border: 1px solid #e2e8f0; background-color: #ffffff; color: #1e293b; border-radius: 6px; padding: 5px;"
                if is_starter_col:
                    base_style = "border: 1px dashed #4f5d75; background-color: #f1f5f9; color: #4f5d75; font-weight: bold; border-radius: 6px; padding: 5px;"
                elif is_special_action:
                    base_style = "border: 1px solid #cbd5e1; background-color: #f1f5f9; color: #0f172a; font-weight: bold; border-radius: 6px; padding: 5px;"
                elif is_flip_button:
                    base_style = "border: 1px solid #cbd5e1; background-color: #f8fafc; color: #d9145a; font-weight: bold; border-radius: 6px; padding: 5px;"

                if self.scanning_state == self.SCAN_ROWS:
                    if r == self.active_row:
                        widget.setStyleSheet("border: 2px solid #d9145a; background-color: #fdf2f8; color: #1e1e24; border-radius: 6px; padding: 5px;")
                    else:
                        widget.setStyleSheet(base_style)
                
                elif self.scanning_state == self.SCAN_COLS:
                    if r == self.active_row and c == self.active_col:
                        widget.setStyleSheet("border: 2px solid #b00f46; background-color: #d9145a; color: #ffffff; font-weight: bold; border-radius: 6px; padding: 5px;")
                    elif r == self.active_row:
                        widget.setStyleSheet("border: 1px solid #d9145a; background-color: #fff1f2; color: #64748b; border-radius: 6px; padding: 5px;")
                    else:
                        widget.setStyleSheet("border: 1px solid #f1f5f9; background-color: #ffffff; color: #cbd5e1; border-radius: 6px; padding: 5px;")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            if self.page_container.currentIndex() == 0:
                self.continue_btn.setEnabled(True)
                self.process_contact_quality({"AF3": 4, "AF4": 4, "T7": 4, "T8": 4, "Pz": 4})
                self.process_eeg_quality({"AF3": 4, "AF4": 4, "T7": 4, "T8": 4, "Pz": 4})
            else:
                if not self.in_cooldown and not self.is_paused:
                    self.trigger_select_event()
        elif event.key() == Qt.Key.Key_S and self.page_container.currentIndex() == 1:
            if not self.in_cooldown and not self.is_paused:
                self.trigger_speed_change()
        elif event.key() == Qt.Key.Key_P and self.page_container.currentIndex() == 1:
            self.process_selection("PAUSE SCANNER")

    # =========================================================================
    # ⏱️ STATE TRACKER OVERRIDE COOLDOWN CONTROLLER
    # =========================================================================
    def trigger_select_event(self):
        if self.scanning_state == self.SCAN_ROWS:
            self.scanning_state = self.SCAN_COLS
            self.active_col = 0
            self.update_ui_highlights()
            self.start_cooldown_phase("Row Locked")

        elif self.scanning_state == self.SCAN_COLS:
            selected_text = self.current_matrix[self.active_row][self.active_col]
            self.process_selection(selected_text)
            
            self.scanning_state = self.SCAN_ROWS
            self.active_row = 0
            self.update_ui_highlights()
            self.start_cooldown_phase("Selection Complete")

    def start_cooldown_phase(self, label_text):
        self.in_cooldown = True
        self.timer.stop() 
        self.cooldown_phase_label = label_text
        self.cooldown_remaining_ms = self.SELECTION_COOLDOWN_MS
        
        self.render_cooldown_in_state_tracker()
        self.cooldown_ticker.start(100) # Ticks every 100ms for high-frequency smooth updates

    def tick_cooldown_countdown(self):
        self.cooldown_remaining_ms -= 100
        if self.cooldown_remaining_ms <= 0:
            self.cooldown_ticker.stop()
            self.end_selection_cooldown()
        else:
            self.render_cooldown_in_state_tracker()

    def render_cooldown_in_state_tracker(self):
        """Replaces standard telemetry text with a highly visible cooldown banner."""
        sec_str = f"{self.cooldown_remaining_ms/1000:.1f}"
        text = f"⏳ BCI PAUSE — [{self.cooldown_phase_label.upper()}]  |  RESUMING IN {sec_str}s  (RELAX MIND / FACE)"
        
        self.telemetry_label.setText(text)
        self.telemetry_label.setStyleSheet("background-color: #d9145a; color: #ffffff; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #b00f46; font-size: 12px; font-weight: bold;")
        
        self.keyboard_network_status_label.setText(f"BCI: Cooldown Active ({sec_str}s)...")
        self.keyboard_network_status_label.setStyleSheet("color: #d9145a; font-weight: bold;")

    def end_selection_cooldown(self):
        self.in_cooldown = False
        self.latch_released = True
        self.facial_latch_released = True
        
        if not self.is_paused:
            self.keyboard_network_status_label.setText("BCI: Scanner Active.")
            self.keyboard_network_status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
            self.timer.start(self.scan_intervals[self.speed_index])
            self.update_telemetry_box("neutral")
            
        self.update_ui_highlights()

    def trigger_speed_change(self):
        self.speed_index = (self.speed_index + 1) % len(self.scan_intervals)
        self.timer.setInterval(self.scan_intervals[self.speed_index])
        self.update_status_bar()

    def update_status_bar(self):
        for i, lbl in enumerate(self.speed_widgets):
            if i == self.speed_index:
                lbl.setStyleSheet("background-color: #d9145a; color: #ffffff; border-radius: 4px; font-weight: bold;")
            else:
                lbl.setStyleSheet("background-color: #e2e8f0; color: #475569; border-radius: 4px;")

    def speak_message(self):
        text_to_speak = self.composed_text.strip()
        if text_to_speak:
            self.tts_worker = TTSThread(text_to_speak)
            self.tts_worker.start()

    def process_selection(self, text):
        if not text or text.strip() == "": return

        if text == "FLIP OVER":
            self.current_board_name = "PHRASES" if self.current_board_name == "ALPHA" else "ALPHA"
            self.current_matrix = self.boards[self.current_board_name]
            self.build_board_grid()
            self.update_status_bar()
            return
            
        elif text == "SPEAK":
            self.speak_message()
            return

        elif text == "BACKSPACE":
            if self.composed_text:
                self.composed_text = self.composed_text[:-1]
            self.display_box.setText(f"Composed Message: {self.composed_text}")
            return

        elif text == "PAUSE SCANNER":
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.timer.stop()
                self.pause_btn.setText("▶️ RESUME")
                self.pause_btn.setStyleSheet("QPushButton { background-color: #2ecc71; color: white; border-radius: 6px; }")
                self.keyboard_network_status_label.setText("BCI: Scanner PAUSED.")
                self.keyboard_network_status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
                self.mental_state_str = "SCANNER PAUSED"
                self.facial_state_str = "SCANNER PAUSED"
                self.update_telemetry_box("locked")
            else:
                self.pause_btn.setText("⏸️ PAUSE")
                self.pause_btn.setStyleSheet("QPushButton { background-color: #f39c12; color: white; border-radius: 6px; }")
                self.keyboard_network_status_label.setText("BCI: Scanner Active.")
                self.keyboard_network_status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
                self.mental_state_str = "NEUTRAL (IDLING) [Power: 0.00]"
                self.facial_state_str = "READY (IDLING)"
                self.update_telemetry_box("neutral")
                self.timer.start(self.scan_intervals[self.speed_index])
            return

        elif text == "SPACE":
            self.composed_text += " "
        elif text == "CLEAR MESSAGE":
            self.composed_text = ""
        elif text in ["WAIT", "PLEASE GUESS"]:
            self.composed_text += f" [{text}] "
        else:
            if len(text) == 1 or text == "QU":
                self.composed_text += text
            else:
                if self.composed_text and not self.composed_text.endswith(" "):
                    self.composed_text += " "
                self.composed_text += text + " "
                
        self.display_box.setText(f"Composed Message: {self.composed_text}")

    def closeEvent(self, event):
        """Immediately terminates all background WebSocket threads and releases the terminal."""
        print("[SYSTEM] Shutting down application...")
        
        # Stop UI timers
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'cooldown_ticker'):
            self.cooldown_ticker.stop()
        event.accept()
        QApplication.quit()
        # Hard-kill the Python process
        import os
        os._exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BCICommunicationBoard()
    window.showMaximized()
    sys.exit(app.exec())