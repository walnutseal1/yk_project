import asyncio
import time
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import yaml

# Import async AI and existing modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.async_ai import AsyncLLM
import memory.memtools as mem
from utils.tool_handler import ToolCallHandler
import utils.context as ct

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
    print("⚠️  Warning: config.yaml not found. Using default values for AsyncSleepTimeAgent.")
    SLEEP_AGENT_MODEL = "ollama/llama3:8b"
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
    Enum to represent the various states of the AsyncSleepTimeAgent.
    """
    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"
    SHUTDOWN = "shutdown"

@dataclass
class MemoryTask:
    """
    Data class to define a memory task that the agent will process.
    """
    data: Any
    created_at: datetime

@dataclass
class SystemEvent:
    """
    Data class to represent system-level events.
    """
    event_type: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

class AsyncSleepTimeAgent:
    """
    High-performance async sleep-time agent with concurrent task processing,
    request balancing, and optimized memory operations.
    
    Key improvements over sync version:
    - Async/await patterns throughout
    - Concurrent task processing
    - Connection pooling for AI requests
    - KV cache for repeated queries
    - Non-blocking event processing
    - Efficient resource management
    """
    
    def __init__(self, max_concurrent_tasks: int = 3):
        """
        Initialize the async sleep-time agent.
        
        Args:
            max_concurrent_tasks: Maximum number of tasks to process concurrently
        """
        
        # Async AI system initialization
        self._llm = None
        self._initialize_ai_task = None
        
        # Timing parameters
        self.min_sleep_interval = MIN_SLEEP_INTERVAL
        self.max_sleep_interval = MAX_SLEEP_INTERVAL
        self.pause_delay_after_main = PAUSE_DELAY_AFTER_MAIN
        
        # State management
        self.state = AgentState.IDLE
        self.main_ai_active = False
        self.last_main_ai_activity = None
        
        # Async queues for better performance
        self.task_queue = asyncio.Queue()
        self.event_queue = asyncio.Queue()
        
        # Concurrent processing controls
        self.max_concurrent_tasks = max_concurrent_tasks
        self._task_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._processing_tasks = set()
        
        # Async task management
        self.main_task = None
        self.event_task = None
        self.shutdown_event = asyncio.Event()
        
        # Thread-safe state management
        self._state_lock = asyncio.Lock()
        self.context = []
        
        print("Async sleep-time agent initialized")
    
    async def finish_edits(self):
        """
        Async version of finish_edits command.
        """
        return None

    async def _initialize_ai_systems(self):
        """
        Async initialization of AI components.
        """
        try:
            # Initialize memory system
            try:
                mem.init_recall_db()
            except Exception as e:
                print(f"Warning: Could not initialize recall DB: {e}")
                pass
            
            # Initialize tool handler with async-compatible tools
            self.handler = ToolCallHandler()
            self.handler.register_tool(mem.vector_get)
            self.handler.register_tool(mem.vector_memory_edit)
            self.handler.register_tool(mem.core_memory_edit)
            self.handler.register_tool(self.finish_edits)
            
            tools = self.handler.get_tool_definitions()
            
            # Initialize async LLM with optimized settings
            self._llm = AsyncLLM(
                model=SLEEP_AGENT_MODEL,
                tools=tools,
                max_tokens=SLEEP_AGENT_CONTEXT,
                max_concurrent_requests=self.max_concurrent_tasks
            )
            
            # Read system prompt
            self.system_prompt = self._read_prompt_from_file(SLEEP_AGENT_PROMPT_PATH)
            
            print("Async sleep-time agent AI systems initialized")
            
        except Exception as e:
            print(f"Failed to initialize async AI systems: {e}")
            raise

    def _read_prompt_from_file(self, file_path: str) -> str:
        """
        Read system prompt from file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Prompt file not found at {file_path}, using empty prompt.")
            return ""
    
    async def start(self):
        """
        Start the async sleep-time agent.
        """
        print("Starting async sleep-time agent...")
        
        # Initialize AI systems
        await self._initialize_ai_systems()
        
        # Start main processing tasks
        self.main_task = asyncio.create_task(self._main_loop())
        self.event_task = asyncio.create_task(self._event_processor())
        
        print("Async sleep-time agent started")
    
    async def stop(self):
        """
        Gracefully stop the agent.
        """
        print("Stopping async sleep-time agent...")
        
        # Signal shutdown
        self.shutdown_event.set()
        
        async with self._state_lock:
            self.state = AgentState.SHUTDOWN
        
        # Cancel main tasks
        if self.main_task:
            self.main_task.cancel()
        if self.event_task:
            self.event_task.cancel()
            
        # Cancel any processing tasks
        for task in list(self._processing_tasks):
            task.cancel()
        
        # Wait for tasks to complete
        tasks_to_wait = []
        if self.main_task:
            tasks_to_wait.append(self.main_task)
        if self.event_task:
            tasks_to_wait.append(self.event_task)
        tasks_to_wait.extend(list(self._processing_tasks))
        
        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)
        
        # Close AI resources
        if self._llm:
            await self._llm.close()
        
        print("Async sleep-time agent stopped.")
    
    async def notify_main_ai_start(self):
        """
        Notify that main AI started processing.
        """
        self.main_ai_active = True
        event = SystemEvent("main_ai_start", datetime.now())
        await self.event_queue.put(event)
    
    async def notify_main_ai_end(self):
        """
        Notify that main AI finished processing.
        """
        self.main_ai_active = False
        event = SystemEvent("main_ai_end", datetime.now())
        await self.event_queue.put(event)
    
    async def go(self, task_input: Any):
        """
        Async version of go - adds task to queue.
        """
        if isinstance(task_input, list) and all(isinstance(item, dict) for item in task_input):
            messages_text = "\n".join([f"{msg.get('role')}: {msg.get('content', '')[:100]}"
                                     for msg in task_input])
            await self.add_task(messages_text)
            print("Added messages to async task queue.")
        elif isinstance(task_input, str):
            await self.add_task(task_input)
            print("Added text to async task queue.")
        else:
            print(f"Warning: Unsupported input type: {type(task_input)}")
    
    async def add_task(self, data: Any):
        """
        Add task to async queue.
        """
        task = MemoryTask(data, datetime.now())
        await self.task_queue.put(task)
        print("Added task to async queue.")
    
    async def _main_loop(self):
        """
        Main async processing loop.
        """
        while not self.shutdown_event.is_set():
            try:
                # Check if should pause
                if await self._should_pause():
                    async with self._state_lock:
                        self.state = AgentState.PAUSED
                    await asyncio.sleep(2)
                    continue
                
                # Process pending tasks concurrently
                if not self.task_queue.empty():
                    async with self._state_lock:
                        self.state = AgentState.PROCESSING
                    
                    try:
                        # Get task with timeout
                        task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                        
                        # Process task concurrently if under limit
                        if len(self._processing_tasks) < self.max_concurrent_tasks:
                            processing_task = asyncio.create_task(self._process_task_wrapper(task))
                            self._processing_tasks.add(processing_task)
                        else:
                            # Queue is full, put task back
                            await self.task_queue.put(task)
                            
                    except asyncio.TimeoutError:
                        pass
                
                # Clean up completed processing tasks
                done_tasks = {task for task in self._processing_tasks if task.done()}
                self._processing_tasks -= done_tasks
                
                # Set to idle and sleep
                async with self._state_lock:
                    self.state = AgentState.IDLE
                
                sleep_time = await self._calculate_sleep_time()
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                print("Main loop cancelled")
                break
            except Exception as e:
                print(f"Error in async main loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_task_wrapper(self, task: MemoryTask):
        """
        Wrapper for processing tasks with semaphore control.
        """
        async with self._task_semaphore:
            try:
                await self._process_task(task)
            except Exception as e:
                print(f"Error processing task: {e}")
            finally:
                # Clean up from processing set
                current_task = asyncio.current_task()
                self._processing_tasks.discard(current_task)
    
    async def _event_processor(self):
        """
        Async event processor.
        """
        while not self.shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                print("Event processor cancelled")
                break
    
    async def _handle_event(self, event: SystemEvent):
        """
        Handle system events.
        """
        if event.event_type == "main_ai_start":
            self.last_main_ai_activity = event.timestamp
        elif event.event_type == "main_ai_end":
            self.last_main_ai_activity = event.timestamp
    
    async def _should_pause(self) -> bool:
        """
        Determine if agent should pause.
        """
        if self.main_ai_active:
            return True
            
        if self.last_main_ai_activity:
            time_since = (datetime.now() - self.last_main_ai_activity).total_seconds()
            return time_since < self.pause_delay_after_main
            
        return False
    
    async def _calculate_sleep_time(self) -> float:
        """
        Calculate appropriate sleep time.
        """
        base_sleep = self.min_sleep_interval
        
        if self.task_queue.empty():
            base_sleep = min(self.max_sleep_interval, base_sleep * 1.2)
            
        return base_sleep
    
    async def _process_task(self, task: MemoryTask):
        """
        Process memory task using async AI.
        """
        print(f"Processing async task created at {task.created_at}")
        
        try:
            # Prepare context
            memory = mem.get_core_memory()
            
            # Append task to context
            self.context.append({"role": "user", "content": task.data})
            system_messages = [{"role": "system", "content": self.system_prompt + "\n" + memory}]
            
            reasoning_loop_active = True
            loop_count = 0
            max_loops = 10
            
            # Async reasoning loop
            while reasoning_loop_active and loop_count < max_loops:
                loop_count += 1
                res_for_assistant_message = ""
                tool_calls = []
                
                # Trim context
                self.context, _ = ct.trim_context(self.context, SLEEP_AGENT_CONTEXT, system_messages=system_messages)
                
                # Async LLM query
                async for chunk in self._llm.query(system_messages + self.context):
                    chunk_type = chunk.get("type")
                    delta = chunk.get("delta")
                    
                    if chunk_type == "content":
                        res_for_assistant_message += delta
                    elif chunk_type == "thinking":
                        # Handle thinking chunks from models like deepseek-r1
                        print(f"[ASYNC SLEEP AGENT THINKING] {delta}")
                    elif chunk_type == "tool_call":
                        tool_calls.append(delta)
                    elif chunk_type == "error":
                        print(f"Async LLM error: {delta}")
                        reasoning_loop_active = False
                        break
                
                # Add assistant response to context
                assistant_message = {"role": "assistant", "content": res_for_assistant_message}
                if tool_calls:
                    assistant_message["tool_calls"] = serialize_obj(tool_calls)
                self.context.append(assistant_message)
                
                # Process tool calls
                if tool_calls:
                    print(f"Processing {len(tool_calls)} async tool calls")
                    
                    # Process tool calls (still sync for now, but could be made async)
                    tool_results = self.handler.process_tool_calls(tool_calls)
                    
                    for tool_result in tool_results:
                        self.context.append({"role": "tool", "content": str(tool_result)})
                    
                    reasoning_loop_active = bool(tool_results)
                else:
                    reasoning_loop_active = True
                    self.context.append({
                        "role": "user", 
                        "content": "[Automated system message] Please try again, no tools were called. If done making edits, call finish_edits function."
                    })
            
            print(f"Completed async task created at {task.created_at}")
            
        except Exception as e:
            print(f"Async task created at {task.created_at} failed: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status.
        """
        async with self._state_lock:
            current_state = self.state.value
        
        return {
            'state': current_state,
            'queue_size': self.task_queue.qsize(),
            'processing_tasks': len(self._processing_tasks),
            'main_ai_active': self.main_ai_active,
            'last_main_ai_activity': self.last_main_ai_activity.isoformat() if self.last_main_ai_activity else None
        }


# Example usage and testing
async def test_async_sleep_agent():
    """Test the async sleep agent."""
    print("Testing AsyncSleepTimeAgent...")
    
    agent = AsyncSleepTimeAgent(max_concurrent_tasks=2)
    
    try:
        await agent.start()
        print("Async agent started successfully")
        
        # Add some test tasks
        await agent.add_task("Test task 1: Summarize recent conversations")
        await agent.add_task("Test task 2: Organize memory blocks")
        
        # Let it run for a bit
        await asyncio.sleep(5)
        
        # Check status
        status = await agent.get_status()
        print(f"Status: {status}")
        
    except KeyboardInterrupt:
        print("Test interrupted")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(test_async_sleep_agent())