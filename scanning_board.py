### ---------------------------------------------------------------------------------- ###
# LEGACY VERSION: Single-Switch Scanning Board (Live Headset Trace Mode)
# Author: Jordan Labio
# Date: 2026-06-15
# Description: This is a legacy version of the BCI Scanning Board that operates in a "Live Headset Trace Mode" for real-time testing and debugging of Emotiv Cortex 
#              mental commands. It is not intended for production use and may lack certain features present in the main application 
#              (setup screen, configuration options, etc.). Use this version for development and testing purposes only.
### ---------------------------------------------------------------------------------- ###


import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

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
    ["PLEASE GUESS", "WAIT", "SPACE", "CLEAR MESSAGE", "", "FLIP OVER"]
]


# --- BACKGROUND EMOTIV CORTEX THREAD WORKER ---
class EmotivCortexWorker(QThread):
    """Background thread that authenticates with Cortex and captures stream commands."""
    mental_command_signal = pyqtSignal(str, float)
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

            def handle_data_packet(*args, **kwargs):
                data = kwargs.get("data", args[0] if args else {})
                print(f"[STREAM RECEIVE] Raw packet incoming: {data}")

                if isinstance(data, dict) and "action" in data and "power" in data:
                    command = str(data["action"])
                    power = float(data["power"])
                    self.mental_command_signal.emit(command, power)
                elif isinstance(data, dict) and "com" in data:
                    command = str(data["com"][0])
                    power = float(data["com"][1])
                    self.mental_command_signal.emit(command, power)
                elif isinstance(data, list) and len(data) >= 2:
                    command = str(data[0])
                    power = float(data[1])
                    self.mental_command_signal.emit(command, power)

            def session_done_callback(*args, **kwargs):
                print("\n==================================================")
                print("[DIAGNOSTIC] Session event handshake complete!")
                
                if profile_name:
                    self.status_signal.emit(f"Loading Profile: {profile_name}...")
                    if hasattr(cortex, "setup_profile"):
                        cortex.setup_profile(profile_name, "load")
                    elif hasattr(cortex, "load_profile"):
                        cortex.load_profile(profile_name)
                
                found_method = False
                for method_name in ["subscribe", "sub_request", "request_sub", "send_subscribe"]:
                    if hasattr(cortex, method_name):
                        print(f"[DIAGNOSTIC] Invoking data pipeline via: cortex.{method_name}()")
                        print("==================================================\n")
                        getattr(cortex, method_name)(["com"])
                        found_method = True
                        break

            cortex.bind(create_session_done=session_done_callback)
            cortex.bind(new_com_data=handle_data_packet)
            
            self.status_signal.emit("Cortex Linked. Awaiting Stream Packets...")
            cortex.open()
            
        except Exception as e:
            self.status_signal.emit(f"Cortex Connection Failed: {e}")


# --- MAIN UI DISPLAY BOARD ENGINE ---
class BCICommunicationBoard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BCI Scanning Board - Live Headset Trace Mode")
        
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

        # BCI Threshold and Latches
        self.ACTIVATION_THRESHOLD = 0.35  
        self.latch_released = True

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        
        self.build_top_display()
        
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.main_layout.addWidget(self.grid_container, stretch=1)
        
        self.build_board_grid()
        self.build_bottom_status()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_scanner)
        self.timer.start(self.scan_intervals[self.speed_index])
        
        self.update_ui_highlights()
        self.update_status_bar()

        # Spin up background worker thread
        self.cortex_thread = EmotivCortexWorker()
        self.cortex_thread.mental_command_signal.connect(self.route_bci_command)
        self.cortex_thread.status_signal.connect(self.display_network_logs)
        self.cortex_thread.start()

    def build_top_display(self):
        self.display_box = QLabel("Composed Message: ")
        self.display_box.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        self.display_box.setStyleSheet("background-color: #1e1e24; color: #00ff66; padding: 15px; border-radius: 8px; border: 2px solid #333;")
        self.display_box.setWordWrap(True)
        self.main_layout.addWidget(self.display_box)

        self.telemetry_label = QLabel("HEADSET STATE: NEUTRAL (IDLING) | Power: 0.00")
        self.telemetry_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.telemetry_label.setStyleSheet("background-color: #2b2d42; color: #edf2f4; padding: 10px; border-radius: 6px; margin-top: 5px; border: 1px solid #4a4e69;")
        self.main_layout.addWidget(self.telemetry_label)

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
                label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
                label.setWordWrap(True)
                label.setStyleSheet("border: 2px solid #dcdcdc; background-color: #ffffff; border-radius: 6px; padding: 5px;")
                self.grid_layout.addWidget(label, r, c)
                row_widgets.append(label)
            self.grid_widgets.append(row_widgets)

    def build_bottom_status(self):
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Mode: AUTOMATIC SCAN")
        self.status_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #333; padding-right: 10px;")
        status_layout.addWidget(self.status_label)
        
        speed_title = QLabel("Speed: ")
        speed_title.setFont(QFont("Arial", 11))
        status_layout.addWidget(speed_title)
        
        self.speed_widgets = []
        for name in self.speed_names:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            lbl.setFixedSize(85, 22)
            status_layout.addWidget(lbl)
            self.speed_widgets.append(lbl)
            
        status_layout.addStretch()

        self.network_status_label = QLabel("BCI: Initializing background service...")
        self.network_status_label.setFont(QFont("Arial", 10, QFont.Weight.Medium))
        self.network_status_label.setStyleSheet("color: #dc3545; padding-right: 15px;")
        status_layout.addWidget(self.network_status_label)
        
        controls_label = QLabel("Push = SELECT  •  Pull = SPEED")
        controls_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        controls_label.setStyleSheet("color: #0056b3; padding: 5px;")
        status_layout.addWidget(controls_label)
        
        self.main_layout.addLayout(status_layout)

    def route_bci_command(self, command, power):
        clean_command = command.strip().lower()

        action_map = {
            "push": "SELECT",
            "pull": "CHANGE SPEED",
            "neutral": "IDLE"
        }
        mapped_action = action_map.get(clean_command, "UNKNOWN")

        if clean_command == "neutral":
            self.telemetry_label.setText(f"HEADSET STATE: NEUTRAL (IDLING) | Power: {power:.2f}")
            self.telemetry_label.setStyleSheet("background-color: #2b2d42; color: #edf2f4; padding: 10px; border-radius: 6px; border: 1px solid #4a4e69;")
            self.latch_released = True
            return

        if power < self.ACTIVATION_THRESHOLD:
            self.telemetry_label.setText(f"HEADSET STATE: {clean_command.upper()} ({mapped_action}) | Power: {power:.2f} (Below 0.35 Threshold)")
            self.telemetry_label.setStyleSheet("background-color: #f4a261; color: #2b2d42; padding: 10px; border-radius: 6px; border: 1px solid #e76f51;")
            self.latch_released = True
            return

        if not self.latch_released:
            self.telemetry_label.setText(f"HEADSET STATE: {clean_command.upper()} ({mapped_action}) | Power: {power:.2f} (LOCKED - Relax mind to reset)")
            self.telemetry_label.setStyleSheet("background-color: #e63946; color: #ffffff; padding: 10px; border-radius: 6px; border: 1px solid #b7094c;")
            return

        print(f"\n[UI TRIGGER] Executing action for command: '{clean_command}' (Power: {power})")
        self.telemetry_label.setText(f"HEADSET STATE: TRIGGERED {clean_command.upper()} ({mapped_action})! | Power: {power:.2f}")
        self.telemetry_label.setStyleSheet("background-color: #2a9d8f; color: #ffffff; padding: 10px; border-radius: 6px; border: 1px solid #1d3557;")
        self.latch_released = False
        
        if clean_command == "push":
            self.trigger_select_event()
        elif clean_command == "pull":
            self.trigger_speed_change()

    def display_network_logs(self, text):
        self.network_status_label.setText(f"BCI: {text}")
        if "Packets" in text:
            self.network_status_label.setStyleSheet("color: #28a745; font-weight: bold;")

    def advance_scanner(self):
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
                
                is_flip_button = (widget.text() == "FLIP OVER")
                is_starter_col = (self.current_board_name == "PHRASES" and c == 0)
                
                if self.scanning_state == self.SCAN_ROWS:
                    if r == self.active_row:
                        if is_flip_button:
                            widget.setStyleSheet("border: 4px solid #003366; background-color: #ff9999; color: #7f0000; font-weight: 900; border-radius: 6px;")
                        else:
                            widget.setStyleSheet("border: 3px solid #003366; background-color: #cbdcf7; color: #000000; border-radius: 6px;")
                    else:
                        if is_flip_button:
                            widget.setStyleSheet("border: 2px solid #bd2130; background-color: #dc3545; color: #ffffff; font-weight: 900; border-radius: 6px;")
                        elif is_starter_col:
                            widget.setStyleSheet("border: 2px solid #5f27cd; background-color: #ddd6ff; color: #341f97; font-weight: bold; border-radius: 6px;")
                        else:
                            widget.setStyleSheet("border: 2px solid #dcdcdc; background-color: #ffffff; color: #000000; border-radius: 6px;")
                
                elif self.scanning_state == self.SCAN_COLS:
                    if r == self.active_row and c == self.active_col:
                        if is_flip_button:
                            widget.setStyleSheet("border: 5px solid #28a745; background-color: #bd2130; color: #ffffff; font-weight: 900; border-radius: 6px;")
                        else:
                            widget.setStyleSheet("border: 4px solid #28a745; background-color: #d4edda; color: #000000; font-weight: bold; border-radius: 6px;")
                    elif r == self.active_row:
                        if is_flip_button:
                            widget.setStyleSheet("border: 2px solid #003366; background-color: #ff9999; color: #7f0000; font-weight: 900; border-radius: 6px;")
                        elif is_starter_col:
                            widget.setStyleSheet("border: 2px solid #003366; background-color: #b2bec3; color: #2d3436; font-weight: bold; border-radius: 6px;")
                        else:
                            widget.setStyleSheet("border: 2px solid #003366; background-color: #f7f9fa; color: #444444; border-radius: 6px;")
                    else:
                        if is_flip_button:
                            widget.setStyleSheet("border: 2px solid #f5c6cb; background-color: #f8d7da; color: #f5c6cb; font-weight: 900; border-radius: 6px;")
                        elif is_starter_col:
                            widget.setStyleSheet("border: 2px solid #f0f0f0; background-color: #f3f0ff; color: #c8c2f2; font-weight: bold; border-radius: 6px;")
                        else:
                            widget.setStyleSheet("border: 2px solid #f0f0f0; background-color: #fafafa; color: #cccccc; border-radius: 6px;")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.trigger_select_event()
        elif event.key() == Qt.Key.Key_S:
            self.trigger_speed_change()

    def trigger_select_event(self):
        if self.scanning_state == self.SCAN_ROWS:
            self.scanning_state = self.SCAN_COLS
            self.active_col = 0
        elif self.scanning_state == self.SCAN_COLS:
            selected_text = self.current_matrix[self.active_row][self.active_col]
            self.process_selection(selected_text)
            self.scanning_state = self.SCAN_ROWS
            self.active_row = 0
        self.update_ui_highlights()

    def trigger_speed_change(self):
        self.speed_index = (self.speed_index + 1) % len(self.scan_intervals)
        self.timer.setInterval(self.scan_intervals[self.speed_index])
        self.update_status_bar()

    def update_status_bar(self):
        for i, lbl in enumerate(self.speed_widgets):
            if i == self.speed_index:
                lbl.setStyleSheet("background-color: #003366; color: #ffffff; border: 1px solid #001122; border-radius: 4px;")
            else:
                lbl.setStyleSheet("background-color: #e0e0e0; color: #888888; border-radius: 4px;")

    def process_selection(self, text):
        if not text or text.strip() == "": return
        if text == "FLIP OVER":
            self.current_board_name = "PHRASES" if self.current_board_name == "ALPHA" else "ALPHA"
            self.current_matrix = self.boards[self.current_board_name]
            self.build_board_grid()
            self.update_status_bar()
            return
        if text == "SPACE":
            self.composed_text += " "
        elif text == "CLEAR MESSAGE":
            self.composed_text = ""
        elif text == "WAIT" or text == "PLEASE GUESS":
            self.composed_text += f" [{text}] "
        else:
            if len(text) == 1 or text == "QU":
                self.composed_text += text
            else:
                if self.composed_text and not self.composed_text.endswith(" "):
                    self.composed_text += " "
                self.composed_text += text + " "
        self.display_box.setText(f"Composed Message: {self.composed_text}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BCICommunicationBoard()
    window.showMaximized()
    sys.exit(app.exec())