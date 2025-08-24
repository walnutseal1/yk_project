import eventlet
eventlet.monkey_patch()

# Don't run this by itself. Launch run.py instead.
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time
import random
import json
import subprocess
import sys
import os
from datetime import datetime
import re
import yaml

# Your existing imports
import utils.ai as ai
import memory.memtools as mem
from utils.tool_handler import ToolCallHandler
import utils.context as ct
import utils.auth as auth
import ipi.webtools as webtools
import ipi.fstools as fstools
from sleep_time.sleeper_agent import SleepTimeAgent

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global variables
gui_process = None
sleep_agent = None

# Load config
try:
    # When run from the 'server' directory, config.yaml is in the parent directory
    with open('../server_config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    MAIN_MODEL = config['main_model']
    CONTEXT_DIR = config['context_dir']
    MAX_TOKENS = config['max_tokens']
    USE_WEB = config['use_web']
    USE_FILESYSTEM = config['use_filesystem']
    PROMPT_DIR = config['prompt_file']
    SLEEP_AGENT_MESSAGE_TRIGGER = config.get('sleep_agent_message_trigger', 0)
except FileNotFoundError:
    print("⚠️  Warning: config.yaml not found. Using default values.")
    MAIN_MODEL = "gpt-4"  # Default model
    CONTEXT_DIR = "context"  # Default context directory
    MAX_TOKENS = 8000  # Default max tokens
    PROMPT_DIR = "prompts/simple.txt"  # Default prompt file
    USE_WEB = False  # Default web tools usage
    USE_FILESYSTEM = False  # Default filesystem tools usage
    SLEEP_AGENT_MESSAGE_TRIGGER = -1

# Initialize context and tools
context = []
handler = None
system_prompt_content = ""

#=============================================================================================================================================================================================================
# Helper Functions from main.py
#=============================================================================================================================================================================================================
def load_prompt(file_path: str) -> str:
    """Loads a prompt from a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️  Warning: Could not load prompt from {file_path}")
        return ""

def serialize_obj(obj):
    """Serialize objects for JSON compatibility."""
    if isinstance(obj, list):
        return [serialize_obj(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: serialize_obj(value) for key, value in obj.items()}
    elif hasattr(obj, "__dict__"):
        return {key: serialize_obj(value) for key, value in obj.__dict__.items()}
    else:
        return obj

def roll_dice(dice_str: str) -> int:
    """
    Roll complex Dungeons & Dragons-style dice expressions. Supports multiple dice and modifiers in one expression.
    
    Args:
        dice_str (str): A dice expression (e.g., "2d6+1d4+2", "d20+2d6-1"). Format: Multiple terms separated by '+' or '-' Dice term: XdY (X = number of dice, defaults to 1 if omitted; Y = sides) Modifier term: just a number (+/-)
        
    Returns:
        int: The sum of all rolls and modifiers.
    
    Example:
        >>> roll_dice("2d6+1d4+2")
        14
    """
    tokens = re.findall(r'[+-]?\d*d?\d+', dice_str.strip().lower())
    total = 0
    
    for token in tokens:
        if 'd' in token:
            sign = -1 if token.startswith('-') else 1
            token = token.lstrip('+-')
            num_dice, sides = token.split('d')
            num_dice = int(num_dice) if num_dice else 1
            sides = int(sides)
            roll_sum = sum(random.randint(1, sides) for _ in range(num_dice))
            total += sign * roll_sum
        else:
            total += int(token)
    
    return f"The result of rolling {dice_str} is {total}."

def send_message(message: str) -> None:
    """Sends a message to the human user.
    
    Args:
        message: Message contents. All unicode (including emojis) are supported.
    
    Returns:
        None
    """
    print(message)
    return None

def initialize_ai_system():
    """Initialize the AI system with tools and memory."""
    global handler, system_prompt_content, context, sleep_agent
    
    try:
        # Initialize memory
        mem.init_recall_db()
        
        # Load system prompt
        system_prompt_content = load_prompt(PROMPT_DIR)
        if not system_prompt_content:
            system_prompt_content = "You are a helpful AI assistant."
        
        # Load context
        context = ct.load_context(CONTEXT_DIR, print_messages=0)  # Don't print on startup
        
        # Initialize the SleepTime agent
        if SLEEP_AGENT_MESSAGE_TRIGGER > 0:
            sleep_agent = SleepTimeAgent()
            sleep_agent.start()
            print("✅ SleepTime agent initialized and started.")

        # Initialize tool handler
        handler = ToolCallHandler()
        handler.register_tool(roll_dice)
        if sleep_agent:
            handler.register_tool(mem.memory_search)
        # Register fstools
        if USE_FILESYSTEM:
            handler.register_tool(fstools.write_file)
            handler.register_tool(fstools.read_file)
            handler.register_tool(fstools.list_directory)
            handler.register_tool(fstools.edit_file)
            handler.register_tool(fstools.search_file_content)
            handler.register_tool(fstools.glob)
        # Register webtools
        if USE_WEB:
            handler.register_tool(webtools.navigate)
            handler.register_tool(webtools.click)
            handler.register_tool(webtools.type_text)
            handler.register_tool(webtools.extract_text)
            handler.register_tool(webtools.extract_html)
            # handler.register_tool(webtools.screenshot)
            # handler.register_tool(webtools.wait_for)
            handler.register_tool(webtools.web_search)
            # handler.register_tool(webtools.http_request)
            # handler.register_tool(webtools.download_file)
            # handler.register_tool(webtools.manage_session)
        
        
        print("✅ AI system initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize AI system: {e}")
        return False

#=============================================================================================================================================================================================================
# Enhanced AI LLM Class
#=============================================================================================================================================================================================================
class EnhancedAILLM:
    def __init__(self):
        self.conversation_history = []
        self.message_counter = 0
        self.ai_initialized = initialize_ai_system()
        if self.ai_initialized:
            tools = handler.get_tool_definitions()
            self.llm = ai.LLM(
                model=MAIN_MODEL,
                tools=tools,
                max_tokens=MAX_TOKENS
            )
        else:
            self.llm = None
    
    def generate_response_stream(self, user_message):
        """Generate streaming response using the new AI system."""
        global context, handler, system_prompt_content

        self.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'user': user_message,
            'ai': ""
        })
        self.message_counter += 1

        if not self.ai_initialized or not self.llm:
            yield from self._mock_response_stream("AI system not initialized.")
            return

        try:
            context.append({"role": "user", "content": user_message})
            reasoning_loop_active = True
            loop_count = 0
            max_loops = 25
            complete_response = ""
            thinking_content = ""
            last_chunk_type = None

            if sleep_agent:
                sleep_agent.notify_main_ai_start() 

            while reasoning_loop_active and loop_count < max_loops:
                loop_count += 1
                res_for_assistant_message = ""
                tool_calls = []
                
                # Refresh prompts for the loop
                if sleep_agent:
                    current_core_memory = mem.get_core_memory()
                else:
                    current_core_memory = ""
                current_system_prompt = [{"role": "system", "content": system_prompt_content + current_core_memory}]
                context_trimmed, trimmed_messages = ct.trim_context(context, MAX_TOKENS, system_messages=current_system_prompt)

                if trimmed_messages:
                    mem.append_to_recall(trimmed_messages)
                    print(f"[Trimmed {len(trimmed_messages)} messages from context]")
                
                context = context_trimmed
                # Use the new LLM class to query
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Assistant: ")
                for chunk in self.llm.query(current_system_prompt + context):
                    print(f"[AI DEBUG] Raw chunk from LLM: {chunk}") # New debug line
                    chunk_type = chunk.get("type")
                    delta = chunk.get("delta")
                    
                    print(delta, end='', flush=True)

                    if chunk_type == "content":
                        if last_chunk_type != 'content' and not delta.strip():
                            continue  # Skip whitespace-only chunks if the last chunk was not content
                        res_for_assistant_message += delta
                        complete_response += delta
                        yield {
                            'type': 'content',
                            'content': complete_response,
                            'is_complete': False
                        }
                    elif chunk_type == "thinking":
                        thinking_content += delta
                        yield {
                            'type': 'thinking',
                            'content': thinking_content,
                            'is_complete': False
                        }
                    elif chunk_type == "tool_call":
                        tool_calls.append(delta)
                        yield {
                            'type': 'tool_call',
                            'content': serialize_obj(delta),
                            'is_complete': False
                        }
                    elif chunk_type == "error":
                        complete_response += f"\n\nERROR: {delta}"
                        reasoning_loop_active = False
                        break
                    
                    last_chunk_type = chunk_type
                
                print(f"[AI DEBUG] Tool calls collected after LLM query: {tool_calls}") # New debug line

                # Append assistant's response and tool calls to context
                assistant_message = {"role": "assistant", "content": res_for_assistant_message}
                if tool_calls:
                    assistant_message["tool_calls"] = serialize_obj(tool_calls)
                context.append(assistant_message)

                if tool_calls:
                    print(f"[AI DEBUG] Tool calls received from LLM: {tool_calls}")
                    tool_results = handler.process_tool_calls(tool_calls)
                    for tool_result in tool_results:
                        context.append({"role": "tool", "content": str(tool_result)})
                        yield {
                            'type': 'tool_result',
                            'content': tool_result,
                            'is_complete': False
                        }
                    if tool_results:
                        reasoning_loop_active = True # Continue loop if tools were called AND tool results were found
                    else:
                        reasoning_loop_active = False
                else:
                    reasoning_loop_active = False # End loop if no tools were called

                if not reasoning_loop_active:
                    break    

            if loop_count >= max_loops:
                complete_response += "\n\n*AI seems to be thinking too hard and got stuck.*"
            
            print() # Newline after the stream

            self.conversation_history[-1]['ai'] = complete_response
            
            if sleep_agent:
                sleep_agent.notify_main_ai_end()
            
                if SLEEP_AGENT_MESSAGE_TRIGGER > 0 and self.message_counter >= SLEEP_AGENT_MESSAGE_TRIGGER:
                    print(f"--- Triggering sleep agent after {self.message_counter} messages ---")
                    
                    # Find the index of the nth to last user message
                    user_message_indices = [i for i, msg in enumerate(context) if msg['role'] == 'user']
                    if len(user_message_indices) >= SLEEP_AGENT_MESSAGE_TRIGGER:
                        start_index = user_message_indices[-SLEEP_AGENT_MESSAGE_TRIGGER]
                        last_n_messages = context[start_index:]
                        sleep_agent.go(last_n_messages)
                        self.message_counter = 0

            yield {
                'type': 'content',
                'content': complete_response,
                'is_complete': True
            }

        except Exception as e:
            error_msg = f"An error occurred: {str(e)}"
            yield {
                'type': 'error',
                'content': error_msg,
                'is_complete': True
            }
    
    def _mock_response_stream(self, message):
        """Fallback mock response for when AI system fails."""
        words = message.split()
        streamed_response = ""
        
        for i, word in enumerate(words):
            if i == 0:
                streamed_response = word
            else:
                streamed_response += " " + word
            
            time.sleep(0.1)
            
            yield {
                'type': 'content',
                'content': streamed_response,
                'is_complete': i == len(words) - 1
            }

def cleanup_gui():
    """Clean up GUI process on exit"""
    global gui_process
    if gui_process and gui_process.poll() is None:
        print("🧹 Cleaning up GUI process...")
        gui_process.terminate()
        try:
            gui_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gui_process.kill()
        print("✅ GUI process cleaned up")

# Initialize the enhanced LLM
llm = EnhancedAILLM()

#=============================================================================================================================================================================================================
# Flask Routes
#=============================================================================================================================================================================================================

@app.route('/chat', methods=['POST'])
def chat():
    """Non-streaming chat endpoint"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                'error': 'No message provided',
                'status': 'error'
            }), 400
        
        user_message = data['message']
        print(f"[{datetime.now().strftime('%H:%M:%S')}] User: {user_message}")
        
        # Generate complete response (non-streaming)
        complete_response = ""
        for chunk in llm.generate_response_stream(user_message):
            if chunk.get('type') == 'content':
                complete_response = chunk.get('content', '')
            if chunk.get('is_complete'):
                break
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] AI: {complete_response}")
        
        return jsonify({
            'response': complete_response,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('send_message')
def handle_send_message(data):
    user_message = data.get('message')
    if not user_message:
        emit('error', {'error': 'No message provided'})
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] User: {user_message}")

    try:
        for chunk in llm.generate_response_stream(user_message):
            chunk['timestamp'] = datetime.now().isoformat()
            emit('stream_chunk', chunk)
            if chunk.get('is_complete'):
                final_content = chunk.get('content', '')
                print(f"[{datetime.now().strftime('%H:%M:%S')}] AI: {final_content}")
                break
    except Exception as e:
        emit('error', {'error': str(e)})

@app.route('/history', methods=['GET'])
def get_history():
    """Get conversation history"""
    return jsonify({
        'history': llm.conversation_history,
        'status': 'success'
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    global gui_process
    
    gui_running = gui_process is not None and gui_process.poll() is None
    
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'streaming_support': True,
        'ai_system_initialized': llm.ai_initialized,
        'gui_status': 'inactive'
    })

@app.route('/clear', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    global context
    llm.conversation_history = []
    context = []  # Also clear the AI context
    return jsonify({
        'status': 'cleared',
        'message': 'Conversation history cleared'
    })

@app.route('/memory/core', methods=['GET'])
def get_core_memory():
    """Get core memory content"""
    if not llm.ai_initialized:
        return jsonify({'error': 'AI system not initialized'}), 500
    
    try:
        core_memory = mem.get_core_memory()
        return jsonify({
            'core_memory': core_memory,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/console', methods=['POST'])
def console_mode():
    """Run the original console interface via API"""
    try:
        data = request.get_json()
        command = data.get('command', '') if data else ''
        
        if command.lower() == 'start':
            # This would start a console session - implementation depends on your needs
            return jsonify({
                'message': 'Console mode would start here. Use the /chat endpoints for interaction.',
                'status': 'info'
            })
        else:
            return jsonify({
                'message': 'Use command: "start" to begin console mode',
                'status': 'info'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sleep_agent/status', methods=['GET'])
def sleep_agent_status():
    """Get sleep time agent status"""
    if not sleep_agent:
        return jsonify({'error': 'sleep time agent not initialized'}), 500
    
    try:
        status = sleep_agent.get_status()
        return jsonify({
            'status': status,
            'success': True
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def main():
    print("=" * 60)
    print("🤖 Enhanced AI Assistant Backend")
    print("=" * 60)
    print("Backend will run on http://localhost:5000")
    print()
    print("Available endpoints:")
    print("  POST /chat - Send a message (non-streaming)")
    print("  GET  /history - Get conversation history")
    print("  GET  /health - Health check")
    print("  POST /clear - Clear conversation history")
    print("  GET  /memory/core - Get core memory")
    print("  POST /console - Console mode commands")
    print("  Websocket events: 'send_message', 'stream_chunk', 'error'")
    print()
    
    if llm.ai_initialized:
        print("✅ AI system initialized successfully")
    else:
        print("⚠️  AI system initialization failed - using fallback mode")
    
    print("🔥 Starting Flask-SocketIO server...")
    print("Press Ctrl+C to stop the server (will also stop GUI)")
    print("=" * 60)
    
    try:
        socketio.run(app, host='localhost', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        cleanup_gui()
        if sleep_agent:
            print("😴 Stopping SleepTime agent...")
            sleep_agent.stop()
            print("✅ SleepTime agent stopped.")
        print("👋 Goodbye!")

if __name__ == '__main__':
    main()
