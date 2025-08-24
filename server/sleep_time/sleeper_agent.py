import threading
import time
import queue
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import yaml

# Import your existing modules
# These imports bring in necessary functionalities from other parts of the project.
import utils.ai as ai  # For AI model interactions
import memory.memtools as mem  # For memory management and tools
from utils.tool_handler import ToolCallHandler # Handles tool execution for the LLM
import utils.context as ct # Potentially for managing conversation context, though not directly used in this file's logic

# Load config
try:
    with open('../server_config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    SLEEP_AGENT_MODEL = config.get('sleep_agent_model')
    SLEEP_AGENT_CONTEXT = config.get('sleep_agent_context')
    MIN_SLEEP_INTERVAL = config.get('min_sleep_interval', 30)
    MAX_SLEEP_INTERVAL = config.get('max_sleep_interval', 300)
    PAUSE_DELAY_AFTER_MAIN = config.get('pause_delay_after_main', 15)
    SLEEP_AGENT_PROMPT_PATH = config.get('sleep_agent_prompt_path', 'prompts/sleep_agent_prompt.txt')

except FileNotFoundError:
    print("⚠️  Warning: config.yaml not found. Using default values for SleepTimeAgent.")
    SLEEP_AGENT_MODEL = "gpt-4"
    SLEEP_AGENT_CONTEXT = 2048
    MIN_SLEEP_INTERVAL = 30
    MAX_SLEEP_INTERVAL = 300
    PAUSE_DELAY_AFTER_MAIN = 15
    SLEEP_AGENT_PROMPT_PATH = 'prompts/sleep_agent_prompt.txt'

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

class AgentState(Enum):
    """
    Enum to represent the various states of the SleepTimeAgent.
    This helps in managing the agent's operational status.
    """
    IDLE = "idle"       # Agent is waiting for tasks or main AI to become inactive
    PROCESSING = "processing" # Agent is actively handling a memory task
    PAUSED = "paused"   # Agent is temporarily halted, usually due to main AI activity
    SHUTDOWN = "shutdown" # Agent is in the process of shutting down

@dataclass
class MemoryTask:
    """
    Data class to define a memory task that the agent will process.
    """
    data: Any # The data for the task, can be text or a list of dicts
    created_at: datetime # Timestamp when the task was created

@dataclass
class SystemEvent:
    """
    Data class to represent system-level events that the agent needs to react to.
    These events can influence the agent's state or trigger new tasks.
    """
    event_type: str     # Type of event (e.g., "main_ai_start", "main_ai_end", "context_trimmed")
    timestamp: datetime # When the event occurred
    metadata: Dict[str, Any] = None # Optional dictionary for additional event details

class SleepTimeAgent:
    """
    A background agent designed to process memory tasks, such as summarizing conversations
    or organizing information, primarily when the main AI system is idle.
    It coordinates its activities to avoid interfering with real-time AI operations.

    ### Queues Used:

    1.  **`self.task_queue` (PriorityQueue):**
        *   **Purpose:** Manages `MemoryTask` objects that the agent needs to process. These tasks are typically related to memory operations like summarizing conversations or processing trimmed context.
        *   **Behavior:** Tasks are added with a `priority` (lower number = higher priority). The `PriorityQueue` ensures that tasks with higher priority are retrieved and processed before lower priority tasks. If priorities are equal, tasks are processed in the order they were added (FIFO).
        *   **Contents:** Stores tuples `(-priority, timestamp, MemoryTask_object)`. The negative priority ensures that Python's `PriorityQueue` (which is a min-heap) correctly orders tasks by highest priority first. The timestamp acts as a tie-breaker for tasks with the same priority.

    2.  **`self.event_queue` (Queue):**
        *   **Purpose:** Handles system-level events that influence the agent's state or trigger new actions. These events include notifications about the main AI starting or ending its activity, or context trimming events.
        *   **Behavior:** A standard FIFO (First-In, First-Out) queue. Events are processed in the order they are received.
        *   **Contents:** Stores `SystemEvent` objects.

    """
    
    def __init__(self):
        """
        Initializes the SleepTimeAgent with configuration and operational parameters.
        """
        
        # Initialize AI systems, including the LLM and tool handler.
        self._initialize_ai_systems()
        
        # Timing parameters for controlling agent's sleep and pause behavior.
        self.min_sleep_interval = MIN_SLEEP_INTERVAL
        self.max_sleep_interval = MAX_SLEEP_INTERVAL
        self.pause_delay_after_main = PAUSE_DELAY_AFTER_MAIN
        
        # State management variables.
        self.state = AgentState.IDLE # Current operational state of the agent
        self.main_ai_active = False # Flag indicating if the main AI is currently active
        self.last_main_ai_activity = None # Timestamp of the last main AI activity
        self.task_queue = queue.Queue() # Queue for memory tasks
        self.event_queue = queue.Queue() # Queue for system events
        
        # Threading components for running the agent's main loop and event processor concurrently.
        self.main_thread = None # Thread for the main processing loop
        self.event_thread = None # Thread for processing system events
        self.shutdown_event = threading.Event() # Event to signal agent shutdown
        self.state_lock = threading.Lock() # Lock to protect concurrent access to agent state
        self.context = [] # Initialize persistent context for the agent
        
        print("Sleep-time agent initialized")
    
    def finish_edits(self):
        """
        Call the finish_edits command when you are finished making edits (integrating all new information) into the memory blocks. This function is called when the agent is done rethinking the memory.

        Marks the current task as finished and updates the agent's state.
        This method is called when a task has been successfully processed.
        """
        return None

    def _initialize_ai_systems(self):
        """
        Initializes the AI components required by the sleep-time agent,
        including the memory system, tool handler, and the Language Model (LLM).
        """
        try:
            # Initialize memory system (if not already initialized)
            # This block attempts to initialize the recall database.
            try:
                mem.init_recall_db()
            except Exception as e: # Catch specific exceptions if known, otherwise log and pass
                # This can happen if the database is already initialized or another process holds a lock.
                # For example, sqlite3.OperationalError: database is locked
                print(f"Warning: Could not initialize recall DB, possibly already initialized or locked: {e}")
                pass
            
            # Initialize tool handler and register memory-related tools.
            # These tools allow the LLM to interact with the memory system.
            self.handler = ToolCallHandler()
            self.handler.register_tool(mem.vector_get)
            self.handler.register_tool(mem.vector_memory_edit)
            self.handler.register_tool(mem.core_memory_edit)
            self.handler.register_tool(self.finish_edits) 
            
            # Get tool definitions in a format suitable for the LLM.
            tools = self.handler.get_tool_definitions()
            
            # Initialize the LLM with the specified model and tools.
            self.llm = ai.LLM(
                model=SLEEP_AGENT_MODEL,
                tools=tools,
                max_tokens=SLEEP_AGENT_CONTEXT
            )
            
            # Define the system prompt for the sleep time agent's LLM.
            # This prompt guides the LLM's behavior as a background memory processor.
            self.system_prompt = self._read_prompt_from_file(SLEEP_AGENT_PROMPT_PATH)
            
            print("sleep time agent AI systems initialized")
            
        except Exception as e:
            # Catching a general Exception to ensure the agent doesn't crash on startup.
            # More granular error handling could be beneficial for specific issues.
            print(f"Failed to initialize AI systems: {e}")
            raise # Re-raises the exception as this is a critical startup failure.

    def _read_prompt_from_file(self, file_path: str) -> str:
        """
        Reads the system prompt from a specified file.
        If the file is not found, it returns empty.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Prompt file not found at {file_path}, using nothing.")
            return ""
    
    def start(self):
        """
        Starts the sleep-time agent by launching its main processing loop
        and event processor in separate daemon threads.
        """
        print("Starting sleep-time agent...")
        
        # Create and start the main processing thread.
        # daemon=True ensures the thread exits when the main program exits.
        self.main_thread = threading.Thread(target=self._main_loop, daemon=True)
        self.event_thread = threading.Thread(target=self._event_processor, daemon=True)
        
        self.main_thread.start()
        self.event_thread.start()
        
        print("Sleep-time agent started")
    
    def stop(self):
        """
        Stops the agent gracefully by setting a shutdown event and joining its threads.
        Also calculates and prints performance metrics.
        """
        print("Stopping sleep-time agent...")
        
        # Signal all threads to shut down.
        self.shutdown_event.set()
        with self.state_lock:
            self.state = AgentState.SHUTDOWN # Update agent state to SHUTDOWN
        
        # Wait for threads to finish, with a timeout.
        if self.main_thread:
            self.main_thread.join(timeout=10)
        if self.event_thread:
            self.event_thread.join(timeout=10)
        
        print(f"Sleep-time agent stopped.")
    
    def notify_main_ai_start(self):
        """
        Notifies the sleep time agent that the main AI has started processing.
        This triggers a system event to potentially pause background tasks.
        """
        self.main_ai_active = True
        event = SystemEvent("main_ai_start", datetime.now())
        self.event_queue.put(event) # Add the event to the event queue for processing
    
    def notify_main_ai_end(self):
        """
        Notifies the sleep time agent that the main AI has finished processing.
        This triggers a system event and potentially queues a summary task.
        """
        self.main_ai_active = False
        event = SystemEvent("main_ai_end", datetime.now())
        self.event_queue.put(event) # Add the event to the event queue for processing
    
    def go(self, task_input: Any):
        """
        Processes input, either as plain text or a list of message dictionaries,
        and adds it to the agent's task queue.
        """
        if isinstance(task_input, list) and all(isinstance(item, dict) for item in task_input):
            # Input is a list of message dictionaries
            messages_text = "\n".join([f"{msg.get('role')}: {msg.get('content', '')[:100]}"
                                     for msg in task_input])
            self.add_task(messages_text)
            print("Added messages to task queue.")
        elif isinstance(task_input, str):
            # Input is regular text
            self.add_task(task_input)
            print("Added text to task queue.")
        else:
            print(f"Warning: Unsupported input type for go function: {type(task_input)}. Input must be a string or a list of dictionaries.")
    
    def add_task(self, data: Any):
        """
        Adds a new memory task to the agent's queue.

        Args:
            data (Any): The data for the task (text or list of dicts).
        """
        task = MemoryTask(data, datetime.now())
        self.task_queue.put(task)
        print(f"Added task to queue.")
    
    def _main_loop(self):
        """
        The main processing loop of the agent.
        It continuously checks for tasks, processes them, and manages its sleep state.
        """
        while not self.shutdown_event.is_set(): # Loop continues until shutdown is signaled
            try:
                # Check if the agent should pause its operations.
                if self._should_pause():
                    with self.state_lock:
                        self.state = AgentState.PAUSED # Update state to PAUSED
                    time.sleep(2) # Short sleep while paused to avoid busy-waiting
                    continue # Skip to the next iteration of the loop
                
                # Process pending tasks if the queue is not empty.
                if not self.task_queue.empty():
                    with self.state_lock:
                        self.state = AgentState.PROCESSING # Update state to PROCESSING
                    
                    try:
                        # Retrieve a task from the queue.
                        task = self.task_queue.get(timeout=1)
                        self._process_task(task) # Process the retrieved task
                        self.task_queue.task_done() # Mark the task as done
                    except queue.Empty:
                        # This can happen if the queue becomes empty between the check and the get() call.
                        pass
                
                # Set to idle state and calculate appropriate sleep time.
                with self.state_lock:
                    self.state = AgentState.IDLE # Update state to IDLE
                
                sleep_time = self._calculate_sleep_time()
                time.sleep(sleep_time) # Agent sleeps for the calculated duration
                
            except Exception as e:
                # Issue: General exception catch. Consider more specific error handling.
                print(f"Error in main loop: {e}")
                time.sleep(5) # Sleep for a bit after an error to prevent rapid error looping
    
    def _event_processor(self):
        """
        Dedicated thread loop for processing system events.
        Events are consumed from the event queue and handled.
        """
        while not self.shutdown_event.is_set(): # Loop continues until shutdown is signaled
            try:
                event = self.event_queue.get(timeout=1) # Get an event from the queue
                self._handle_event(event) # Handle the retrieved event
                self.event_queue.task_done() # Mark the event as done
            except queue.Empty:
                # Continue if no events are in the queue
                continue
    
    def _handle_event(self, event: SystemEvent):
        """
        Handles different types of system events, updating agent state or queuing new tasks.

        Args:
            event (SystemEvent): The system event to be handled.
        """
        if event.event_type == "main_ai_start":
            self.last_main_ai_activity = event.timestamp # Record when main AI started
            
        elif event.event_type == "main_ai_end":
            self.last_main_ai_activity = event.timestamp # Record when main AI ended
            # No immediate task queuing here; tasks are handled by the main loop based on queue status.
            
        
    
    def _should_pause(self) -> bool:
        """
        Determines if the agent should pause its background processing.
        It pauses if the main AI is active or if it recently finished activity.

        Returns:
            bool: True if the agent should pause, False otherwise.
        """
        if self.main_ai_active:
            return True # Pause if main AI is currently active
            
        if self.last_main_ai_activity:
            # Calculate time since last main AI activity.
            time_since = (datetime.now() - self.last_main_ai_activity).total_seconds()
            return time_since < self.pause_delay_after_main # Pause if within the delay period
            
        return False # Do not pause if no recent main AI activity
    
    def _calculate_sleep_time(self) -> float:
        """
        Calculates the duration the agent should sleep before its next cycle.
        Sleep time increases if the task queue is empty to reduce resource usage.

        Returns:
            float: The calculated sleep time in seconds.
        """
        base_sleep = self.min_sleep_interval # Start with the minimum sleep interval
        
        if self.task_queue.empty():
            # If no tasks, gradually increase sleep time up to max_sleep_interval.
            base_sleep = min(self.max_sleep_interval, base_sleep * 1.5) # Issue: This multiplication might not be ideal for gradual increase.
                                                                        # It could jump quickly. Consider a more linear or exponential backoff.
        return base_sleep
    
    def _process_task(self, task: MemoryTask):
        """
        Processes a single memory task using the LLM and registered tools.
        This involves constructing a prompt, querying the LLM, and handling tool calls.

        Args:
            task (MemoryTask): The task to be processed.
        """
        print(f"Processing task created at {task.created_at}")
        
        try:
            # Prepare context for the LLM query.
            memory = mem.get_core_memory()
            
            # Append the current task's prompt to the persistent context.
            self.context.append({"role": "user", "content": task.data})
            system_messages = [{"role": "system", "content": self.system_prompt + "\n" + memory}]
            
            reasoning_loop_active = True
            loop_count = 0
            max_loops = 10 # Maximum number of iterations for the reasoning loop
            
            # Main reasoning loop: LLM generates response, potentially calls tools, and loop continues if tools are called.
            while reasoning_loop_active and loop_count < max_loops:
                loop_count += 1
                res_for_assistant_message = "" # Accumulates content from LLM chunks
                tool_calls = [] # Accumulates tool calls from LLM chunks
                
                # Trim context before querying the LLM to ensure it stays within token limits.
                # The system messages are accounted for in the token count but not trimmed from 'self.context'.
                self.context, _ = ct.trim_context(self.context, SLEEP_AGENT_CONTEXT, system_messages=system_messages)
                
                # Query the LLM and process its streamed output chunks.
                for chunk in self.llm.query(system_messages + self.context):
                    chunk_type = chunk.get("type")
                    delta = chunk.get("delta")
                    
                    if chunk_type == "content":
                        res_for_assistant_message += delta
                    elif chunk_type == "tool_call":
                        tool_calls.append(delta)
                    elif chunk_type == "error":
                        print(f"LLM error: {delta}")
                        reasoning_loop_active = False # Stop loop on LLM error
                        break
                
                # Add the assistant's full response (content + tool calls) to the context.
                assistant_message = {"role": "assistant", "content": res_for_assistant_message}
                if tool_calls:
                    assistant_message["tool_calls"] = serialize_obj(tool_calls)
                self.context.append(assistant_message)
                
                # Process any tool calls generated by the LLM.
                if tool_calls:
                    print(f"Processing {len(tool_calls)} tool calls")
                    tool_results = self.handler.process_tool_calls(tool_calls)
                    
                    # Add tool results back to the context for the next LLM turn.
                    for tool_result in tool_results:
                        self.context.append({"role": "tool", "content": str(tool_result)})
                    
                    if tool_results:
                        reasoning_loop_active = True  # Continue loop if tools were called and results obtained
                    else:
                        reasoning_loop_active = False # End loop if tools were called but no results (e.g., failed)
                else:
                    reasoning_loop_active = True  # Continue loop if no tools were called by the LLM, and warn it.
                    self.context.append({"role": "user", "content": "[This is an automated system message hidden from the user] Please try again, no tools were called. If you are done making edits, call the finish_edits function."})
            
            print(f"Completed task created at {task.created_at}")
            
        except Exception as e:
            # Issue: General exception catch. Consider more specific error handling for task processing.
            print(f"Task created at {task.created_at} failed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Retrieves the current operational status and performance metrics of the agent.

        Returns:
            Dict[str, Any]: A dictionary containing various status indicators.
        """
        with self.state_lock:
            current_state = self.state.value # Get current state safely
        
        return {
            'state': current_state,
            'queue_size': self.task_queue.qsize(), # Number of tasks currently in the queue
            'main_ai_active': self.main_ai_active,
            'last_main_ai_activity': self.last_main_ai_activity.isoformat() if self.last_main_ai_activity else None # Format timestamp for readability
        }

# Example usage block for testing the SleepTimeAgent.
if __name__ == "__main__":
    # Create an instance of the SleepTimeAgent.
    sleep_agent = SleepTimeAgent()
    
    try:
        sleep_agent.start() # Start the agent's background threads
        print("sleep time agent running... Press Ctrl+C to stop")
        
        # Keep the main thread alive to allow daemon threads to run.
        # Periodically print the agent's status.
        while True:
            time.sleep(10)
            status = sleep_agent.get_status()
            print(f"Status: {status['state']}, Queue: {status['queue_size']}")
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sleep_agent.stop() # Ensure the agent is stopped gracefully on exit
