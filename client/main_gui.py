import sys
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# Fix Qt high DPI scaling issue - MUST be called before QApplication
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
    print("⚠️  Warning: config.yaml not found. Using default values.")
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
                padding: 5px;
                background-color: rgba(255, 105, 180, 0.1);
                border-radius: 5px;
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
    def __init__(self, title, section_type="default", parent=None): # Added section_type
        super().__init__(parent)
        self.is_expanded = False
        self.section_type = section_type # Store section type
        
        # Apply AI bubble styling to the section itself
        bubble_color = "rgba(255, 105, 180, 0.1)" # AI bubble background
        border_color = "#ff69b4" # AI bubble border
        
        self.setStyleSheet(f"""
            CollapsibleSection {{
                background-color: {bubble_color};
                border: 1px solid {border_color};
                border-radius: 10px;
                margin: 5px 0px 5px 0px; /* Add vertical margin */
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5) # Add some padding inside the section
        layout.setSpacing(2)
        
        self.toggle_button = QPushButton(f"Show {title}")
        self.toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bubble_color}; /* Apply bubble background */
                color: {border_color}; /* Match AI bubble border color */
                border: 1px solid {border_color}; /* Apply bubble border */
                border-radius: 8px; /* Apply rounded corners */
                padding: 5px;
                text-align: left;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 105, 180, 0.2); /* Slightly darker on hover */
                color: #ffffff; /* Lighter color on hover */
            }}
        """)
        self.toggle_button.clicked.connect(self.toggle)
        
        layout.addWidget(self.toggle_button)

        if self.section_type == "tool_calls":
            self.tab_widget = QTabWidget()
            self.tab_widget.setStyleSheet("""
                QTabWidget::pane { /* The tab widget frame */
                    border: 1px solid #ff69b4;
                    border-radius: 8px;
                    background-color: transparent;
                }
                QTabBar::tab {
                    background: #3c3c3c;
                    color: white;
                    border: 1px solid #ff69b4;
                    border-bottom-color: #ff69b4; /* same as pane color */
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 5px 10px;
                }
                QTabBar::tab:selected {
                    background: #ff69b4;
                    color: white;
                    border-color: #ff69b4;
                    border-bottom-color: #ff69b4; /* same as pane color */
                }
                QTabBar::tab:hover {
                    background: rgba(255, 105, 180, 0.2);
                }
            """)
            self.tab_widget.setVisible(False)

            self.tool_call_text_edit = QTextEdit()
            self.tool_call_text_edit.setReadOnly(True)
            self.tool_call_text_edit.setMaximumHeight(200)
            self.tool_call_text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: transparent;
                    color: #ddd;
                    border: none; /* Handled by QTabWidget::pane */
                    padding: 5px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                }}
            """)
            self.tab_widget.addTab(self.tool_call_text_edit, "Tool Call")

            self.tool_result_text_edit = QTextEdit()
            self.tool_result_text_edit.setReadOnly(True)
            self.tool_result_text_edit.setMaximumHeight(200)
            self.tool_result_text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: transparent;
                    color: #ddd;
                    border: none; /* Handled by QTabWidget::pane */
                    padding: 5px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                }}
            """)
            self.tab_widget.addTab(self.tool_result_text_edit, "Tool Result")
            layout.addWidget(self.tab_widget)
            self.content_widget = self.tab_widget # Set content_widget for toggle
        else: # Default to single QTextEdit for "Thinking"
            self.content_area = QTextEdit()
            self.content_area.setReadOnly(True)
            self.content_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.content_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.content_area.setStyleSheet(f"""
                QTextEdit {{
                    background-color: transparent; /* Inherit parent background */
                    color: #ddd;
                    border: 1px solid {border_color}; /* Add a border */
                    border-radius: 8px; /* Rounded border */
                    padding: 5px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                }}
            """)
            self.content_area.setVisible(False)
            self.content_area.textChanged.connect(self.adjust_height)
            layout.addWidget(self.content_area)
            self.content_widget = self.content_area # Set content_widget for toggle
        
    def adjust_height(self):
        doc_height = self.content_area.document().size().height()
        self.content_area.setFixedHeight(int(doc_height) + 10)

    def toggle(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded) # Use content_widget
        self.toggle_button.setText(
            f"Hide {self.toggle_button.text().split(' ')[1]}" if self.is_expanded else f"Show {self.toggle_button.text().split(' ')[1]}"
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
    def __init__(self, sender, timestamp, is_user=False): # Removed message parameter
        super().__init__()
        self.is_user = is_user
        self.setup_ui(sender, timestamp) # Removed message parameter
    
    def setup_ui(self, sender, timestamp): # Removed message parameter
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 5, 10, 5)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Align content to top
        
        # Header with sender and timestamp
        header_layout = QHBoxLayout()
        
        sender_label = QLabel(sender)
        sender_label.setStyleSheet(f"""
            font-weight: bold;
            color: {'#00ffff' if self.is_user else '#ff69b4'};
            font-size: 14px;
        """)
        
        timestamp_label = QLabel(timestamp)
        timestamp_label.setStyleSheet("""
            color: #888;
            font-size: 11px;
        """)
        
        header_layout.addWidget(sender_label)
        header_layout.addStretch()
        header_layout.addWidget(timestamp_label)
        
        self.main_layout.addLayout(header_layout)
        
        # Bubble styling
        bubble_color = "rgba(0, 255, 255, 0.1)" if self.is_user else "rgba(255, 105, 180, 0.1)"
        border_color = "#00ffff" if self.is_user else "#ff69b4"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bubble_color};
                border: 1px solid {border_color};
                border-radius: 10px;
                /* Removed fixed margin here, alignment will be handled by parent layout */
            }}
        """)
    # Removed update_message method

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
        self.setGeometry(100, 100, 900, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Header with status and controls
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #3c3c3c;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        
        self.status_label = QLabel("Checking backend status...")
        self.status_label.setStyleSheet("color: orange; padding: 5px; font-weight: bold;")
        
        self.streaming_toggle = QCheckBox("Streaming Mode")
        self.streaming_toggle.setChecked(True)
        self.streaming_toggle.setStyleSheet("""
            QCheckBox {
                color: white;
                font-weight: bold;
            }
            QCheckBox::indicator:checked {
                background-color: #ff69b4;
                border: 2px solid #ff69b4;
            }
        """)
        self.streaming_toggle.toggled.connect(self.toggle_streaming_mode)
        
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        header_layout.addWidget(self.streaming_toggle)
        
        main_layout.addWidget(header_frame)
        
        # Chat display area with scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px solid #ff69b4;
                border-radius: 10px;
                background-color: #2b2b2b;
            }
            QScrollBar:vertical {
                background-color: #3c3c3c;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #ff69b4;
                border-radius: 6px;
                min-height: 20px;
            }
        """)
        
        # Chat content widget
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(5)
        
        # Typing indicator
        self.typing_indicator = TypingIndicator()
        self.typing_indicator.hide()
        self.chat_layout.addWidget(self.typing_indicator)
        
        self.scroll_area.setWidget(self.chat_content)
        main_layout.addWidget(self.scroll_area)
        
        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #3c3c3c;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setStyleSheet("""
            QLineEdit {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #666;
                border-radius: 5px;
                background-color: #4a4a4a;
                color: white;
            }
            QLineEdit:focus {
                border-color: #ff69b4;
            }
        """)
        
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #ff69b4;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #ff1493;
            }
            QPushButton:pressed {
                background-color: #dc143c;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
        """)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        main_layout.addWidget(input_frame)
        
        # Bottom controls
        controls_frame = QFrame()
        controls_layout = QHBoxLayout(controls_frame)
        
        self.clear_button = QPushButton("Clear Chat")
        self.status_button = QPushButton("Check Status")
        
        button_style = """
            QPushButton {
                background-color: #666;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #888;
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
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #1e1e1e;
                color: white;
            }
        """)
        
        # Welcome messages
        self.add_system_message("🤖 Welcome to AI Chat Interface with Streaming!")
        self.add_system_message("💫 Make sure your Flask backend is running on localhost:5000")
        self.add_system_message("✨ Streaming mode is enabled for real-time responses")
    
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
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        system_label = QLabel(f"[{timestamp}] {message}")
        system_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-style: italic;
                padding: 5px 10px;
                margin: 2px 0px;
                background-color: rgba(255, 255, 255, 0.05);
                border-left: 3px solid #ff69b4;
                border-radius: 3px;
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
        self.add_system_message(f"❌ Error: {error}")
        
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
                self.add_system_message("🧹 Chat history cleared!")
            else:
                self.add_system_message("🧹 Local chat cleared (server clear failed)")
    
    def check_backend_status(self):
        online, info = self.client.health_check()
        
        if online:
            streaming_support = info.get('streaming_support', False) if info else False
            status_text = "✅ Backend Status: Online"
            if streaming_support:
                status_text += " (Streaming Supported)"
                
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: green; padding: 5px; font-weight: bold;")
            self.add_system_message("🌐 Backend connection successful!")
        else:
            self.status_label.setText("❌ Backend Status: Offline")
            self.status_label.setStyleSheet("color: red; padding: 5px; font-weight: bold;")
            self.add_system_message("🚫 Cannot connect to backend. Make sure Flask server is running!")

    def closeEvent(self, event):
        # Clean shutdown
        if hasattr(self, 'streaming_thread'):
            self.streaming_thread.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    # Create and show main window
    window = ChatWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
