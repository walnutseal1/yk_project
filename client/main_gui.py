import sys

# Fix Windows console encoding for unicode support
import os
if os.name == 'nt':  # Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Fix Qt high DPI scaling issue - MUST be called before ANY Qt imports
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
os.environ['QT_SCALE_FACTOR_ROUNDING_POLICY'] = 'PassThrough'

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# Set high DPI policy after imports but before QApplication
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

import requests
import json
import yaml
import socketio
from datetime import datetime
try:
    # When run from the 'client' directory, client_config.yaml is in the parent directory
    with open('../client_config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    USER = config['user']
    ASSISTANT = config['assistant']
except FileNotFoundError:
    print("Warning: config.yaml not found. Using default values.")
    USER = "You"
    ASSISTANT = "AI"

class WebSocketClient:
    def __init__(self, backend_url="http://localhost:5000"):
        self.sio = socketio.Client()
        self.backend_url = backend_url
        self.connected = False

    def connect(self):
        try:
            self.sio.connect(self.backend_url)
            self.connected = True
        except socketio.exceptions.ConnectionError as e:
            print(f"Socket.IO connection error: {e}")
            self.connected = False

    def disconnect(self):
        if self.connected:
            self.sio.disconnect()
            self.connected = False

    def send_message(self, message):
        if self.connected:
            self.sio.emit('send_message', {'message': message})

    def on_stream_chunk(self, callback):
        self.sio.on('stream_chunk', callback)

    def on_error(self, callback):
        self.sio.on('error', callback)
    
    def send_message_normal(self, message):
        """Send message and get complete response (fallback)"""
        try:
            response = requests.post(
                f"{self.backend_url}/chat",
                json={'message': message},
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['response']
            else:
                return f"Server error: {response.status_code}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def health_check(self):
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=5)
            return response.status_code == 200, response.json() if response.status_code == 200 else None
        except:
            return False, None
    
    def clear_history(self):
        try:
            response = requests.post(f"{self.backend_url}/clear", timeout=5)
            return response.status_code == 200
        except:
            return False

class StreamingThread(QThread):
    chunk_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client = WebSocketClient()
    
    def send_message(self, message):
        self.client.send_message(message)
    
    def run(self):
        if not self.client.connected:
            self.client.connect()

        if self.client.connected:
            self.client.on_stream_chunk(self.chunk_received.emit)
            self.client.on_error(lambda data: self.error_occurred.emit(data.get('error', 'Unknown error')))
            # Keep the thread alive to receive messages
            self.client.sio.wait()
        else:
            self.error_occurred.emit("Failed to connect to the WebSocket server.")

    def stop(self):
        self.client.disconnect()
        self.quit()
        self.wait()

class TypingIndicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText(f"{ASSISTANT} is typing")
        self.setStyleSheet("""
            QLabel {
                color: #ff69b4;
                font-style: italic;
                padding: 12px 20px;
                background: rgba(255, 105, 180, 0.15);
                border: 1px solid rgba(255, 105, 180, 0.4);
                border-radius: 20px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        
        # Animation for typing indicator
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_dots)
        self.dots = 0
        self.base_text = f"{ASSISTANT} is typing"
        
    def start_animation(self):
        self.dots = 0
        self.timer.start(500)  # Update every 500ms
        self.show()
        
    def stop_animation(self):
        self.timer.stop()
        self.hide()
        
    def update_dots(self):
        self.dots = (self.dots + 1) % 4
        self.setText(self.base_text + "." * self.dots)

class CollapsibleSection(QWidget):
    def __init__(self, title, section_type="default", parent=None):
        super().__init__(parent)
        self.is_expanded = False
        self.section_type = section_type
        
        # Apply clean AI bubble styling to the section itself
        if section_type == "thinking":
            bubble_color = "rgba(255, 215, 0, 0.15)"
            border_color = "rgba(255, 215, 0, 0.4)"
        else:  # tool_calls
            bubble_color = "rgba(138, 43, 226, 0.15)"
            border_color = "rgba(138, 43, 226, 0.4)"
        
        self.setStyleSheet(f"""
            CollapsibleSection {{
                background: {bubble_color};
                border: 1px solid {border_color};
                border-radius: 12px;
                margin: 8px 0px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Clean toggle button
        self.toggle_button = QPushButton(f"🔽 Show {title}")
        self.toggle_button.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.1);
                color: {'#ffd700' if section_type == 'thinking' else '#8a2be2'};
                border: 1px solid {border_color};
                border-radius: 12px;
                padding: 10px 15px;
                text-align: left;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.3);
            }}
        """)
        self.toggle_button.clicked.connect(self.toggle)
        
        layout.addWidget(self.toggle_button)

        if self.section_type == "tool_calls":
            self.tab_widget = QTabWidget()
            self.tab_widget.setStyleSheet("""
                QTabWidget::pane {
                    border: 1px solid rgba(138, 43, 226, 0.4);
                    border-radius: 12px;
                    background: rgba(255, 255, 255, 0.05);
                }
                QTabBar::tab {
                    background: rgba(255, 255, 255, 0.1);
                    color: white;
                    border: 1px solid rgba(138, 43, 226, 0.4);
                    border-bottom-color: rgba(138, 43, 226, 0.4);
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    padding: 8px 15px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background: rgba(138, 43, 226, 0.6);
                    color: white;
                    border-color: rgba(138, 43, 226, 0.6);
                    border-bottom-color: rgba(138, 43, 226, 0.6);
                }
                QTabBar::tab:hover {
                    background: rgba(138, 43, 226, 0.3);
                }
            """)
            self.tab_widget.setVisible(False)

            self.tool_call_text_edit = QTextEdit()
            self.tool_call_text_edit.setReadOnly(True)
            self.tool_call_text_edit.setMaximumHeight(200)
            self.tool_call_text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background: rgba(255, 255, 255, 0.03);
                    color: #ddd;
                    border: none;
                    padding: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                    border-radius: 8px;
                }}
            """)
            self.tab_widget.addTab(self.tool_call_text_edit, "🔧 Tool Call")

            self.tool_result_text_edit = QTextEdit()
            self.tool_result_text_edit.setReadOnly(True)
            self.tool_result_text_edit.setMaximumHeight(200)
            self.tool_result_text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background: rgba(255, 255, 255, 0.03);
                    color: #ddd;
                    border: none;
                    padding: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                    border-radius: 8px;
                }}
            """)
            self.tab_widget.addTab(self.tool_result_text_edit, "📊 Tool Result")
            layout.addWidget(self.tab_widget)
            self.content_widget = self.tab_widget
        else:  # Default to single QTextEdit for "Thinking"
            self.content_area = QTextEdit()
            self.content_area.setReadOnly(True)
            self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.content_area.setStyleSheet(f"""
                QTextEdit {{
                    background: rgba(255, 255, 255, 0.03);
                    color: #ddd;
                    border: 1px solid {border_color};
                    border-radius: 12px;
                    padding: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                }}
            """)
            self.content_area.setVisible(False)
            self.content_area.textChanged.connect(self.adjust_height)
            layout.addWidget(self.content_area)
            self.content_widget = self.content_area
        
    def adjust_height(self):
        doc_height = self.content_area.document().size().height()
        self.content_area.setFixedHeight(int(doc_height) + 10)

    def toggle(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        self.toggle_button.setText(
            f"🔼 Hide {self.toggle_button.text().split(' ')[2]}" if self.is_expanded else f"🔽 Show {self.toggle_button.text().split(' ')[2]}"
        )
        if self.is_expanded and self.section_type == "thinking":
            self.adjust_height()
        elif not self.is_expanded and self.section_type == "thinking":
            self.content_area.setFixedHeight(0)
    
    def append_text(self, text, tab_type="tool_call"):
        if not self.isVisible():
            self.setVisible(True)
        if self.section_type == "tool_calls":
            if tab_type == "tool_call":
                self.tool_call_text_edit.append(text)
                self.tab_widget.setCurrentWidget(self.tool_call_text_edit)
            elif tab_type == "tool_result":
                self.tool_result_text_edit.append(text)
                self.tab_widget.setCurrentWidget(self.tool_result_text_edit)
        else: # For "Thinking" section
            self.content_area.setPlainText(text) # Changed to setPlainText

class ChatBubble(QFrame):
    def __init__(self, sender, timestamp, is_user=False):
        super().__init__()
        self.is_user = is_user
        self.setup_ui(sender, timestamp)
    
    def setup_ui(self, sender, timestamp):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 10, 15, 10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setSpacing(8)
        
        # Header with sender and timestamp
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        sender_label = QLabel(sender)
        sender_label.setStyleSheet(f"""
            font-weight: bold;
            color: {'#00ffff' if self.is_user else '#ff69b4'};
            font-size: 14px;
            padding: 5px 10px;
            background: rgba({'0, 255, 255' if self.is_user else '255, 105, 180'}, 0.1);
            border: 1px solid rgba({'0, 255, 255' if self.is_user else '255, 105, 180'}, 0.3);
            border-radius: 15px;
        """)
        
        timestamp_label = QLabel(timestamp)
        timestamp_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.6);
            font-size: 11px;
            padding: 3px 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
        """)
        
        header_layout.addWidget(sender_label)
        header_layout.addStretch()
        header_layout.addWidget(timestamp_label)
        
        self.main_layout.addLayout(header_layout)
        
        # Clean bubble styling with solid colors
        if self.is_user:
            bubble_color = "rgba(0, 255, 255, 0.15)"
            border_color = "rgba(0, 255, 255, 0.4)"
        else:
            bubble_color = "rgba(255, 105, 180, 0.15)"
            border_color = "rgba(255, 105, 180, 0.4)"
        
        self.setStyleSheet(f"""
            QFrame {{
                background: {bubble_color};
                border: 1px solid {border_color};
                border-radius: 20px;
                margin: 8px 0px;
            }}
        """)

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_ai_bubble = None
        self.current_thinking_section = None
        self.current_tool_calls_section = None
        self.streaming_enabled = True
        self.setup_ui()
        self.setup_streaming_client()
        self.check_backend_status()
        
    def setup_ui(self):
        self.setWindowTitle("AI Chat Interface - Streaming Enabled")
        self.setGeometry(100, 100, 1200, 800)  # Larger window for better layout
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout with modern spacing
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Clean header with subtle styling
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setSpacing(15)
        
        # Status indicator with clean design
        self.status_label = QLabel("Checking backend status...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ffd700;
                padding: 8px 15px;
                font-weight: bold;
                font-size: 13px;
                background: rgba(255, 215, 0, 0.1);
                border: 1px solid rgba(255, 215, 0, 0.3);
                border-radius: 20px;
            }
        """)
        
        # Clean streaming toggle
        self.streaming_toggle = QCheckBox("Streaming Mode")
        self.streaming_toggle.setChecked(True)
        self.streaming_toggle.setStyleSheet("""
            QCheckBox {
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 15px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 10px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                background: rgba(255, 255, 255, 0.1);
            }
            QCheckBox::indicator:checked {
                background: #ff69b4;
                border-color: rgba(255, 255, 255, 0.5);
            }
            QCheckBox:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.streaming_toggle.toggled.connect(self.toggle_streaming_mode)
        
        # Clean model selector
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("""
            QComboBox {
                color: white;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 12px;
                padding: 10px 15px;
                min-width: 200px;
                font-weight: bold;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: rgba(255, 105, 180, 0.5);
                background: rgba(255, 255, 255, 0.08);
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border-style: solid;
                border-width: 4px 4px 0 4px;
                border-color: transparent transparent rgba(255, 255, 255, 0.8) transparent;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 0.95);
                color: white;
                selection-background-color: rgba(255, 105, 180, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                outline: none;
            }
        """)
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        self.load_available_models()
        
        # Clean sleep model selector
        self.sleep_model_combo = QComboBox()
        self.sleep_model_combo.setStyleSheet("""
            QComboBox {
                color: white;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 12px;
                padding: 10px 15px;
                min-width: 200px;
                font-weight: bold;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: rgba(105, 180, 255, 0.5);
                background: rgba(255, 255, 255, 0.08);
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border-style: solid;
                border-width: 4px 4px 0 4px;
                border-color: transparent transparent rgba(255, 255, 255, 0.8) transparent;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 0.95);
                color: white;
                selection-background-color: rgba(105, 180, 255, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                outline: none;
            }
        """)
        self.sleep_model_combo.currentTextChanged.connect(self.on_sleep_model_changed)
        self.load_sleep_models()
        
        # Clean sleep agent controls
        sleep_agent_frame = QFrame()
        sleep_agent_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 105, 180, 0.1);
                border: 1px solid rgba(255, 105, 180, 0.3);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        sleep_agent_layout = QHBoxLayout(sleep_agent_frame)
        sleep_agent_layout.setSpacing(10)
        
        # Clean sleep agent status
        self.sleep_agent_status = QLabel("Sleep Agent: Unknown")
        self.sleep_agent_status.setStyleSheet("""
            color: #ff69b4; 
            font-size: 12px; 
            padding: 8px 12px;
            background: rgba(255, 105, 180, 0.1);
            border: 1px solid rgba(255, 105, 180, 0.3);
            border-radius: 15px;
        """)
        
        # Clean trigger button
        self.trigger_sleep_agent_btn = QPushButton("🚀 Trigger Sleep Agent")
        self.trigger_sleep_agent_btn.setStyleSheet("""
            QPushButton {
                background: #ff69b4;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ff1493;
            }
            QPushButton:pressed {
                background: #c71585;
            }
        """)
        self.trigger_sleep_agent_btn.clicked.connect(self.trigger_sleep_agent)
        
        # Clean labels
        chat_model_label = QLabel("💬 Chat Model:")
        chat_model_label.setStyleSheet("""
            color: white; 
            font-weight: bold; 
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
        """)
        
        sleep_model_label = QLabel("😴 Sleep Model:")
        sleep_model_label.setStyleSheet("""
            color: white; 
            font-weight: bold; 
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
        """)
        
        # Organize header layout
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        header_layout.addWidget(chat_model_label)
        header_layout.addWidget(self.model_combo)
        header_layout.addWidget(sleep_model_label)
        header_layout.addWidget(self.sleep_model_combo)
        header_layout.addWidget(sleep_agent_frame)
        header_layout.addWidget(self.streaming_toggle)
        
        # Add sleep agent controls to the frame
        sleep_agent_layout.addWidget(self.sleep_agent_status)
        sleep_agent_layout.addWidget(self.trigger_sleep_agent_btn)
        
        main_layout.addWidget(header_frame)
        
        # Clean chat display area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid rgba(255, 105, 180, 0.3);
                border-radius: 12px;
                background: rgba(43, 43, 43, 0.8);
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 14px;
                border-radius: 7px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #ff69b4;
                border-radius: 7px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #ff1493;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Chat content widget with clean spacing
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(12)
        self.chat_layout.setContentsMargins(20, 20, 20, 20)
        
        # Clean typing indicator
        self.typing_indicator = TypingIndicator()
        self.typing_indicator.hide()
        self.chat_layout.addWidget(self.typing_indicator)
        
        # Set up periodic status refresh timer
        self.status_refresh_timer = QTimer()
        self.status_refresh_timer.timeout.connect(self.refresh_sleep_agent_status)
        self.status_refresh_timer.start(10000)  # Refresh every 10 seconds
        
        self.scroll_area.setWidget(self.chat_content)
        main_layout.addWidget(self.scroll_area)
        
        # Clean input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 15px;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setSpacing(15)
        
        # Clean message input
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("💭 Type your message here...")
        self.message_input.setStyleSheet("""
            QLineEdit {
                padding: 15px 20px;
                font-size: 14px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.05);
                color: white;
            }
            QLineEdit:focus {
                border-color: #ff69b4;
                background: rgba(255, 255, 255, 0.08);
            }
            QLineEdit::placeholder {
                color: rgba(255, 255, 255, 0.5);
                font-style: italic;
            }
        """)
        
        # Clean send button
        self.send_button = QPushButton("🚀 Send")
        self.send_button.setStyleSheet("""
            QPushButton {
                background: #ff69b4;
                color: white;
                border: none;
                padding: 15px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 12px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #ff1493;
            }
            QPushButton:pressed {
                background: #c71585;
            }
            QPushButton:disabled {
                background: rgba(100, 100, 100, 0.5);
                color: rgba(255, 255, 255, 0.5);
            }
        """)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        main_layout.addWidget(input_frame)
        
        # Clean bottom controls
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 12px;
            }
        """)
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setSpacing(15)
        
        self.clear_button = QPushButton("🗑️ Clear Chat")
        self.status_button = QPushButton("📊 Check Status")
        
        # Clean button styling
        button_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 10px 20px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
        """
        
        self.clear_button.setStyleSheet(button_style)
        self.status_button.setStyleSheet(button_style)
        
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.status_button)
        controls_layout.addStretch()
        
        main_layout.addWidget(controls_frame)
        
        # Connect signals
        self.send_button.clicked.connect(self.send_message)
        self.message_input.returnPressed.connect(self.send_message)
        self.clear_button.clicked.connect(self.clear_chat)
        self.status_button.clicked.connect(self.check_backend_status)
        
        # Clean dark theme
        self.setStyleSheet("""
            QMainWindow {
                background: #1a1a2e;
            }
            QWidget {
                background: transparent;
                color: white;
            }
        """)
        
        # Welcome messages
        self.add_system_message("🎉 Welcome to AI Chat Interface with Streaming!")
        self.add_system_message("🔧 Make sure your Flask backend is running on localhost:5000")
        self.add_system_message("⚡ Streaming mode is enabled for real-time responses")
    
    def setup_streaming_client(self):
        self.streaming_thread = StreamingThread()
        self.streaming_thread.chunk_received.connect(self.handle_streaming_chunk)
        self.streaming_thread.error_occurred.connect(self.handle_error)
        self.client = self.streaming_thread.client # Use the client from the thread
        self.streaming_thread.start()
    
    def toggle_streaming_mode(self, enabled):
        self.streaming_enabled = enabled
        mode = "Streaming" if enabled else "Standard"
        self.setWindowTitle(f"AI Chat Interface - {mode} Mode")
        self.add_system_message(f"💡 Switched to {mode} mode")
    
    def add_chat_bubble(self, sender, message_content, is_user=False, is_streaming=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        bubble = ChatBubble(sender, timestamp, is_user) # Updated constructor call
        
        # For user messages, the content is final and set immediately
        if is_user:
            message_label = QLabel(message_content)
            message_label.setWordWrap(True)
            message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            message_label.setStyleSheet("""
                color: white;
                font-size: 13px;
                padding: 8px;
                line-height: 1.4;
                background-color: transparent;
                border: none;
            """)
            bubble.main_layout.addWidget(message_label)
        
        if is_streaming:
            self.current_ai_bubble = bubble
        
        # Insert before typing indicator
        insert_index = self.chat_layout.count() - 1  # Before typing indicator
        self.chat_layout.insertWidget(insert_index, bubble) # Reverted to direct insertion
        
        # Auto-scroll to bottom
        QTimer.singleShot(50, self.scroll_to_bottom)
        
        return bubble
    
    def add_system_message(self, message):
        # Guard against calling before UI is fully initialized
        if not hasattr(self, 'chat_layout'):
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        system_label = QLabel(f"📢 [{timestamp}] {message}")
        system_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.8);
                font-style: italic;
                padding: 10px 15px;
                margin: 5px 0px;
                background: rgba(255, 255, 255, 0.08);
                border-left: 4px solid #ff69b4;
                border-radius: 12px;
                font-size: 12px;
            }
        """)
        system_label.setWordWrap(True)
        
        # Insert before typing indicator
        insert_index = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_index, system_label)
        
        QTimer.singleShot(50, self.scroll_to_bottom)
    
    def scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def send_message(self):
        message = self.message_input.text().strip()
        if not message:
            return
        
        # Add user message
        self.add_chat_bubble(USER, message, is_user=True)
        
        # Clear input and disable send button
        self.message_input.clear()
        self.send_button.setEnabled(False)
        self.send_button.setText("Sending...")
        
        if self.streaming_enabled:
            # Show typing indicator and start streaming
            self.typing_indicator.start_animation()
            self.streaming_thread.send_message(message)
        else:
            # Use standard non-streaming mode
            self.add_system_message("🔄 Processing message...")
            # You could implement a non-streaming thread here if needed
            # For now, we'll just use streaming but show it differently
            self.streaming_thread.send_message(message)
    
    def handle_streaming_chunk(self, data):
        if 'error' in data:
            self.handle_error(data['error'])
            return

        chunk_type = data.get('type')
        
        if chunk_type == 'ping':
            # This is just a keep-alive, ignore it
            return
            
        is_complete = data.get('is_complete', False)

        self.typing_indicator.stop_animation()

        # Ensure current_ai_bubble exists for any AI-generated content
        if not self.current_ai_bubble:
            self.current_ai_bubble = self.add_chat_bubble(ASSISTANT, "", is_streaming=True)
            # Reset internal sections when a new AI bubble is created
            self.current_thinking_section = None
            self.current_tool_calls_section = None
            self.current_message_section = None # New: Track the message widget

        # Get the last widget in the current AI bubble to check if we need to append to it
        last_widget_item = self.current_ai_bubble.main_layout.itemAt(self.current_ai_bubble.main_layout.count() - 1)
        last_widget = last_widget_item.widget() if last_widget_item else None

        if chunk_type == 'thinking':
            content = data.get('content', '')
            if isinstance(last_widget, CollapsibleSection) and last_widget.section_type == "thinking":
                self.current_thinking_section = last_widget
            else:
                self.current_thinking_section = CollapsibleSection("Thinking", section_type="thinking")
                self.current_ai_bubble.main_layout.addWidget(self.current_thinking_section)
            self.current_thinking_section.append_text(content)

        elif chunk_type in ['tool_call', 'tool_result']:
            content = data.get('content')
            if isinstance(last_widget, CollapsibleSection) and last_widget.section_type == "tool_calls":
                self.current_tool_calls_section = last_widget
            else:
                self.current_tool_calls_section = CollapsibleSection("Tool Calls", section_type="tool_calls")
                self.current_ai_bubble.main_layout.addWidget(self.current_tool_calls_section)

            formatted_content = json.dumps(content, indent=2)
            if chunk_type == 'tool_call':
                self.current_tool_calls_section.append_text(formatted_content, tab_type="tool_call")
            else: # tool_result
                self.current_tool_calls_section.append_text(formatted_content, tab_type="tool_result")

        elif chunk_type == 'content':
            content = data.get('content', '')
            # Check if the last widget is already a content label
            if isinstance(last_widget, QLabel) and getattr(last_widget, 'section_type', None) == "content":
                self.current_message_section = last_widget
            else:
                self.current_message_section = QLabel()
                self.current_message_section.section_type = "content" # Add identifier
                self.current_message_section.setWordWrap(True)
                self.current_message_section.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.current_message_section.setStyleSheet("""
                    color: white;
                    font-size: 13px;
                    padding: 8px;
                    line-height: 1.4;
                    background-color: transparent;
                    border: none;
                """)
                self.current_ai_bubble.main_layout.addWidget(self.current_message_section)
            self.current_message_section.setText(content)

        # Auto-scroll as content updates
        QTimer.singleShot(10, self.scroll_to_bottom)

        if is_complete:
            # Response is complete
            self.current_ai_bubble = None
            self.current_thinking_section = None # Clear for next response
            self.current_tool_calls_section = None # Clear for next response
            self.current_message_section = None # Clear for next response
            self.typing_indicator.stop_animation()
            self.send_button.setEnabled(True)
            self.send_button.setText("Send")
            self.message_input.setFocus()
    
    def handle_error(self, error):
        self.typing_indicator.stop_animation()
        self.add_system_message(f"Error: {error}")
        
        # Re-enable send button
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")
        self.message_input.setFocus()
        
        # Clear current AI bubble if it exists
        self.current_ai_bubble = None
        self.current_thinking_section = None
        self.current_tool_calls_section = None
    
    def clear_chat(self):
        reply = QMessageBox.question(
            self, 
            "Clear Chat", 
            "Are you sure you want to clear the chat history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Clear all chat bubbles except system messages and typing indicator
            for i in reversed(range(self.chat_layout.count())):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), ChatBubble):
                    item.widget().deleteLater()
            
            if self.client.clear_history():
                self.add_system_message("Chat history cleared!")
            else:
                self.add_system_message("Local chat cleared (server clear failed)")
    
    def load_available_models(self):
        """Load available models from Ollama tags endpoint"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                
                # Clear existing items
                self.model_combo.clear()
                
                # Add models with detailed categories
                chat_models = []
                thinking_models = []
                embedding_models = []
                vision_models = []
                code_models = []
                other_models = []
                
                for model in models:
                    model_name = model.get('name', '')
                    details = model.get('details', {})
                    family = details.get('family', '').lower()
                    families = details.get('families', [])
                    parameter_size = details.get('parameter_size', '')
                    
                    # Categorize models based on multiple criteria
                    model_lower = model_name.lower()
                    
                    # Thinking models (reasoning models) - expanded detection
                    if any(think in model_lower for think in [
                        'deepseek-r1', 'gpt-oss', 'o1', 'reasoning',
                        'granite3.3', 'granite3.2', 'granite-3',  # Granite models
                        'qwen3:8b', 'qwen3-8b',  # Larger Qwen3 models often have reasoning
                        'llama3.1:8b', 'llama3.1-8b',  # Larger Llama models
                        'r1', 'think', 'reason'
                    ]):
                        thinking_models.append((model_name, parameter_size))
                    # Embedding models
                    elif 'embed' in model_lower or 'embedding' in model_lower:
                        embedding_models.append((model_name, parameter_size))
                    # Vision models  
                    elif ('vision' in model_lower or 'clip' in families or 
                          any(vis in model_lower for vis in ['llava', 'pixtral', 'qwen2.5vl'])):
                        vision_models.append((model_name, parameter_size))
                    # Code models
                    elif any(code in model_lower for code in ['coder', 'code', 'starcoder', 'codellama']):
                        code_models.append((model_name, parameter_size))
                    # Chat models (general conversation)
                    elif any(fam in family for fam in ['llama', 'qwen', 'granite', 'phi', 'mistral', 'gemma']):
                        chat_models.append((model_name, parameter_size))
                    else:
                        other_models.append((model_name, parameter_size))
                
                # Add categorized models to combo box with parameter sizes
                if thinking_models:
                    self.model_combo.addItem("--- 🧠 Thinking Models ---")
                    for model_name, size in sorted(thinking_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                        
                if chat_models:
                    self.model_combo.addItem("--- 💬 Chat Models ---")
                    for model_name, size in sorted(chat_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                
                if vision_models:
                    self.model_combo.addItem("--- 👁️ Vision Models ---")
                    for model_name, size in sorted(vision_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                
                if code_models:
                    self.model_combo.addItem("--- 💻 Code Models ---")
                    for model_name, size in sorted(code_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                
                if embedding_models:
                    self.model_combo.addItem("--- 🔍 Embedding Models ---")  
                    for model_name, size in sorted(embedding_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                
                if other_models:
                    self.model_combo.addItem("--- ⚙️ Other Models ---")
                    for model_name, size in sorted(other_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.model_combo.addItem(display_text)
                
                # Set current model if available (prioritize thinking > chat > others)
                if thinking_models:
                    first_model = thinking_models[0][0]
                    self.model_combo.setCurrentText(f"{first_model} ({thinking_models[0][1]})" if thinking_models[0][1] else first_model)
                elif chat_models:
                    first_model = chat_models[0][0]
                    self.model_combo.setCurrentText(f"{first_model} ({chat_models[0][1]})" if chat_models[0][1] else first_model)
                    
            else:
                self.model_combo.addItem("Connection Failed")
                
        except requests.exceptions.RequestException:
            self.model_combo.addItem("Ollama Not Available")
    
    def load_sleep_models(self):
        """Load available models for sleep agent from Ollama tags endpoint"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                
                # Clear existing items
                self.sleep_model_combo.clear()
                
                # Add models with detailed categories
                chat_models = []
                thinking_models = []
                embedding_models = []
                vision_models = []
                code_models = []
                other_models = []
                
                for model in models:
                    model_name = model.get('name', '')
                    details = model.get('details', {})
                    family = details.get('family', '').lower()
                    families = details.get('families', [])
                    parameter_size = details.get('parameter_size', '')
                    
                    # Categorize models based on multiple criteria
                    model_lower = model_name.lower()
                    
                    # Thinking models (reasoning models) - expanded detection
                    if any(think in model_lower for think in [
                        'deepseek-r1', 'gpt-oss', 'o1', 'reasoning',
                        'granite3.3', 'granite3.2', 'granite-3',  # Granite models
                        'qwen3:8b', 'qwen3-8b',  # Larger Qwen3 models often have reasoning
                        'llama3.1:8b', 'llama3.1-8b',  # Larger Llama models
                        'r1', 'think', 'reason'
                    ]):
                        thinking_models.append((model_name, parameter_size))
                    # Embedding models
                    elif 'embed' in model_lower or 'embedding' in model_lower:
                        embedding_models.append((model_name, parameter_size))
                    # Vision models  
                    elif ('vision' in model_lower or 'clip' in families or 
                          any(vis in model_lower for vis in ['llava', 'pixtral', 'qwen2.5vl'])):
                        vision_models.append((model_name, parameter_size))
                    # Code models
                    elif any(code in model_lower for code in ['coder', 'code', 'starcoder', 'codellama']):
                        code_models.append((model_name, parameter_size))
                    # Chat models (general conversation)
                    elif any(fam in family for fam in ['llama', 'qwen', 'granite', 'phi', 'mistral', 'gemma']):
                        chat_models.append((model_name, parameter_size))
                    else:
                        other_models.append((model_name, parameter_size))
                
                # Add categorized models to combo box with parameter sizes
                if thinking_models:
                    self.sleep_model_combo.addItem("--- 🧠 Thinking Models ---")
                    for model_name, size in sorted(thinking_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                        
                if chat_models:
                    self.sleep_model_combo.addItem("--- 💬 Chat Models ---")
                    for model_name, size in sorted(chat_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                
                if vision_models:
                    self.sleep_model_combo.addItem("--- 👁️ Vision Models ---")
                    for model_name, size in sorted(vision_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                
                if code_models:
                    self.sleep_model_combo.addItem("--- 💻 Code Models ---")
                    for model_name, size in sorted(code_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                
                if embedding_models:
                    self.sleep_model_combo.addItem("--- 🔍 Embedding Models ---")  
                    for model_name, size in sorted(embedding_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                
                if other_models:
                    self.sleep_model_combo.addItem("--- ⚙️ Other Models ---")
                    for model_name, size in sorted(other_models):
                        display_text = f"{model_name} ({size})" if size else model_name
                        self.sleep_model_combo.addItem(display_text)
                
                # Set current model - prefer lightweight models for sleep agent (prioritize chat > thinking > others)
                if chat_models:
                    first_model = chat_models[0][0]
                    self.sleep_model_combo.setCurrentText(f"{first_model} ({chat_models[0][1]})" if chat_models[0][1] else first_model)
                elif thinking_models:
                    first_model = thinking_models[0][0]
                    self.sleep_model_combo.setCurrentText(f"{first_model} ({thinking_models[0][1]})" if thinking_models[0][1] else first_model)
                    
            else:
                self.sleep_model_combo.addItem("Connection Failed")
                
        except requests.exceptions.RequestException:
            self.sleep_model_combo.addItem("Ollama Not Available")
    
    def on_sleep_model_changed(self, model_name):
        """Handle sleep agent model selection change"""
        if model_name and not model_name.startswith("---") and "Failed" not in model_name:
            # Send sleep model change request to backend
            try:
                response = requests.post(
                    f"http://localhost:5000/set_sleep_model",
                    json={"model": f"ollama/{model_name}"},
                    timeout=5
                )
                if response.status_code == 200:
                    self.add_system_message(f"Switched sleep agent to model: {model_name}")
                else:
                    self.add_system_message(f"Failed to switch sleep agent model: {model_name}")
            except requests.exceptions.RequestException:
                self.add_system_message("Could not connect to backend to change sleep model")
    
    def on_model_changed(self, model_name):
        """Handle model selection change"""
        if model_name and not model_name.startswith("---") and "Failed" not in model_name:
            # Send model change request to backend
            try:
                response = requests.post(
                    f"http://localhost:5000/set_model",
                    json={"model": f"ollama/{model_name}"},
                    timeout=5
                )
                if response.status_code == 200:
                    self.add_system_message(f"Switched to model: {model_name}")
                else:
                    self.add_system_message(f"Failed to switch model: {model_name}")
            except requests.exceptions.RequestException:
                self.add_system_message("Could not connect to backend to change model")
    
    def check_backend_status(self):
        online, info = self.client.health_check()
        
        if online:
            streaming_support = info.get('streaming_support', False) if info else False
            status_text = "Backend Status: Online"
            if streaming_support:
                status_text += " (Streaming Supported)"
                
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: green; padding: 5px; font-weight: bold;")
            self.add_system_message("Backend connection successful!")
            
            # Update sleep agent status
            self.update_sleep_agent_status(info)
        else:
            self.status_label.setText("Backend Status: Offline")
            self.status_label.setStyleSheet("color: red; padding: 5px; font-weight: bold;")
            self.add_system_message("Cannot connect to backend. Make sure Flask server is running!")
            self.sleep_agent_status.setText("Sleep Agent: Offline")
    
    def update_sleep_agent_status(self, health_info):
        """Update sleep agent status display based on backend health info"""
        if health_info and 'sleep_agent' in health_info:
            sleep_info = health_info['sleep_agent']
            if sleep_info.get('initialized', False):
                status = sleep_info.get('status', {})
                if status and 'state' in status:
                    state = status['state']
                    queue_size = status.get('queue_size', 0)
                    self.sleep_agent_status.setText(f"Sleep Agent: {state.title()} (Queue: {queue_size})")
                    
                    # Color code based on state
                    if state == 'idle':
                        self.sleep_agent_status.setStyleSheet("color: #00ff00; font-size: 11px; padding: 3px;")
                    elif state == 'processing':
                        self.sleep_agent_status.setStyleSheet("color: #ffff00; font-size: 11px; padding: 3px;")
                    elif state == 'paused':
                        self.sleep_agent_status.setStyleSheet("color: #ff8800; font-size: 11px; padding: 3px;")
                    else:
                        self.sleep_agent_status.setStyleSheet("color: #ff69b4; font-size: 11px; padding: 3px;")
                else:
                    self.sleep_agent_status.setText("Sleep Agent: Active")
                    self.sleep_agent_status.setStyleSheet("color: #00ff00; font-size: 11px; padding: 3px;")
            else:
                self.sleep_agent_status.setText("Sleep Agent: Not Initialized")
                self.sleep_agent_status.setStyleSheet("color: #888888; font-size: 11px; padding: 3px;")
        else:
            self.sleep_agent_status.setText("Sleep Agent: Unknown")
            self.sleep_agent_status.setStyleSheet("color: #888888; font-size: 11px; padding: 3px;")
    
    def trigger_sleep_agent(self):
        """Manually trigger the sleep agent to process current context"""
        try:
            response = requests.post(
                "http://localhost:5000/sleep_agent/trigger",
                json={"force": True},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.add_system_message(f"Sleep agent triggered successfully! Processing {data.get('context_size', 0)} messages.")
                # Update status after a short delay
                QTimer.singleShot(2000, self.refresh_sleep_agent_status)
            else:
                error_data = response.json()
                self.add_system_message(f"Failed to trigger sleep agent: {error_data.get('error', 'Unknown error')}")
                
        except requests.exceptions.RequestException as e:
            self.add_system_message(f"Could not connect to backend to trigger sleep agent: {str(e)}")
    
    def refresh_sleep_agent_status(self):
        """Refresh sleep agent status from backend"""
        try:
            online, info = self.client.health_check()
            if online:
                self.update_sleep_agent_status(info)
        except:
            pass  # Silently fail if backend is not available

    def closeEvent(self, event):
        # Clean shutdown
        if hasattr(self, 'streaming_thread'):
            self.streaming_thread.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Clean dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 46))  # #1a1a2e
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 33, 62))    # #16213e
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(15, 52, 96))  # #0f3460
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(26, 26, 46))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 105, 180))  # Hot pink
    palette.setColor(QPalette.ColorRole.Link, QColor(105, 180, 255))        # Blue
    palette.setColor(QPalette.ColorRole.Highlight, QColor(255, 105, 180, 100))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    # Set application properties
    app.setApplicationName("AI Chat Interface")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("YK Project")
    
    # Create and show main window
    window = ChatWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
