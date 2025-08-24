import json
import sqlite3
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import deque
import yaml
import ai  # or your preferred LLM client

try:
    with open('../server_config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    COMPRESSOR_MODEL = config['compressor_model']
    MAX_TOKENS = config['compressor_max_tokens']
except FileNotFoundError or KeyError:
    print("⚠️  Warning: config.yaml not found. Using default values.")
    COMPRESSOR_MODEL = "gpt-4"  # Default model
    MAX_TOKENS = 8000  # Default max tokens

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: dotenv not installed, environment variables will not be loaded.")


@dataclass
class Message:
    content: str
    role: str  # 'user' or 'assistant'
    timestamp: datetime
    
@dataclass
class TaskNode:
    name: str
    path: str
    messages: List[Message]
    compressed_messages: Optional[List[Dict[str, str]]] = None
    integrated_compressions: Optional[List[Dict[str, str]]] = None  # Compressed children inserted here
    compression_hash: Optional[str] = None
    is_active: bool = True
    created_at: datetime = None
    last_modified: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_modified is None:
            self.last_modified = datetime.now()

class THCFStorage:
    """Handles persistent storage using SQLite for scalability"""
    
    def __init__(self, db_path: str = "thcf.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tasks table for metadata and compressed messages
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                path TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                compressed_messages TEXT,
                integrated_compressions TEXT,
                compression_hash TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP,
                last_modified TIMESTAMP
            )
        ''')
        
        # Messages table for full conversation history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_path TEXT,
                content TEXT,
                role TEXT,
                timestamp TIMESTAMP,
                FOREIGN KEY (task_path) REFERENCES tasks (path)
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_path ON messages(task_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)')
        
        conn.commit()
        conn.close()
    
    def save_task(self, task: TaskNode):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save task metadata
        cursor.execute('''
            INSERT OR REPLACE INTO tasks 
            (path, name, compressed_messages, integrated_compressions, compression_hash, is_active, created_at, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task.path, task.name, 
            json.dumps(task.compressed_messages) if task.compressed_messages else None,
            json.dumps(task.integrated_compressions) if task.integrated_compressions else None,
            task.compression_hash,
            task.is_active, task.created_at, task.last_modified
        ))
        
        # Delete existing messages for this task to prevent duplicates
        cursor.execute('DELETE FROM messages WHERE task_path = ?', (task.path,))
        
        # Save current messages
        for msg in task.messages:
            cursor.execute('''
                INSERT INTO messages (task_path, content, role, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (task.path, msg.content, msg.role, msg.timestamp))
        
        conn.commit()
        conn.close()
    
    def load_task(self, path: str) -> Optional[TaskNode]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load task metadata
        cursor.execute('SELECT * FROM tasks WHERE path = ?', (path,))
        task_row = cursor.fetchone()
        
        if not task_row:
            conn.close()
            return None
        
        # Load messages
        cursor.execute('''
            SELECT content, role, timestamp FROM messages 
            WHERE task_path = ? ORDER BY timestamp
        ''', (path,))
        
        messages = [
            Message(content=row[0], role=row[1], timestamp=row[2])
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return TaskNode(
            name=task_row[1],
            path=task_row[0],
            compressed_messages=json.loads(task_row[2]) if task_row[2] else None,
            integrated_compressions=json.loads(task_row[3]) if task_row[3] else None,
            compression_hash=task_row[4],
            is_active=bool(task_row[5]),
            created_at=task_row[6],
            last_modified=task_row[7],
            messages=messages
        )
    
    def get_child_tasks(self, parent_path: str) -> List[str]:
        """Get all direct child task paths"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find tasks that are direct children (one level deeper)
        if not parent_path.endswith('/'):
            parent_path += '/'
            
        cursor.execute('''
            SELECT path FROM tasks 
            WHERE path LIKE ? AND path != ?
            AND (LENGTH(path) - LENGTH(REPLACE(path, '/', ''))) = 
                (LENGTH(?) - LENGTH(REPLACE(?, '/', '')) + 1)
        ''', (f"{parent_path}%", parent_path.rstrip('/'), parent_path, parent_path))
        
        result = [row[0] for row in cursor.fetchall()]
        conn.close()
        return result

class THCFCompressor:
    """Handles task compression by extracting key input/output pairs"""
    
    def __init__(self):
        self.client = ai.LLM(model=COMPRESSOR_MODEL, temperature=1, max_tokens=MAX_TOKENS)
        self.max_tokens = MAX_TOKENS
    
    async def compress_task_with_children(self, task: TaskNode, child_compressions: List[Dict]) -> List[Dict[str, str]]:
        """Compress a task into essential user/assistant pairs, including child work"""
        
        # Start with child compressions
        compressed_messages = []
        for child_compression in child_compressions:
            compressed_messages.extend(child_compression)
        
        # Add this task's messages
        all_messages = compressed_messages + [
            {"role": msg.role, "content": msg.content} 
            for msg in task.messages
        ]
        
        if not all_messages:
            return []
        
        # Prepare messages for compression prompt
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in all_messages
        ])
        
        prompt = f"""
        From the provided conversation, extract only persistent, reusable knowledge. Omit casual chatter or one-time events unless they change future decisions. Separate facts from actions. For each fact, include: detail, relevant topics/tags, source date/time, and optional confidence score. Keep language clear and concise for later recall. Output in structured JSON with fields: facts (list of objects), tags (list), source_tasks (list of IDs). Avoid long narratives or summaries; focus on distilled, future-useful information only.Return ONLY the essential user/assistant pairs in this exact format:
        user: [essential request]
        assistant: [final answer/result]
        user: [next essential request]  
        assistant: [final answer/result]
        """
        
        full_response_content = []
        
        # The ai.LLM.query method returns an iterator for streaming
        for chunk in self.client.query(
            messages=[{"role": "user", "content": prompt}, {"role": "user", "content": conversation_text}],
        ):
            if chunk.get("type") == "content":
                full_response_content.append(chunk["delta"])
            # Handle other chunk types if necessary, e.g., "thinking", "tool_call"
        
        compressed_text = "".join(full_response_content).strip()
        return self._parse_compressed_messages(compressed_text)
    
    def _parse_compressed_messages(self, compressed_text: str) -> List[Dict[str, str]]:
        """Parse compressed text back into message list"""
        messages = []
        lines = compressed_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('user: '):
                messages.append({
                    "role": "user",
                    "content": line[6:]  # Remove "user: "
                })
            elif line.startswith('assistant: '):
                messages.append({
                    "role": "assistant", 
                    "content": line[11:]  # Remove "assistant: "
                })
        
        return messages
    
    async def compress_task(self, task: TaskNode) -> List[Dict[str, str]]:
        """Compress a task without children (backward compatibility)"""
        return await self.compress_task_with_children(task, [])

class THCFContextManager:
    """Handles context assembly and caching"""
    
    def __init__(self, storage: THCFStorage, max_context_tokens: int = 8000):
        self.storage = storage
        self.max_context_tokens = max_context_tokens
        self.context_cache = {}  # Simple in-memory cache
    
    def get_task_path_hierarchy(self, task_path: str) -> List[str]:
        """Get all ancestor paths for a given task path"""
        parts = task_path.strip('/').split('/')
        paths = []
        
        for i in range(1, len(parts) + 1):
            paths.append('/' + '/'.join(parts[:i]))
        
        return paths
    
    def assemble_context(self, current_task_path: str) -> List[Dict[str, str]]:
        """Assemble context: raw messages from direct path + integrated compressions"""
        messages = []
        
        # Get the direct path from root to current task
        path_hierarchy = self.get_task_path_hierarchy(current_task_path)
        
        # For each level in the direct path (excluding current task)
        for i, path in enumerate(path_hierarchy[:-1]):  # Exclude current task
            task = self.storage.load_task(path)
            if not task:
                continue
            
            # Add the task's own raw messages
            for msg in task.messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add integrated compressions from completed sibling branches  
            if task.integrated_compressions:
                messages.extend(task.integrated_compressions)
        
        # Add current task's raw messages (not compressed yet)
        current_task = self.storage.load_task(current_task_path)
        if current_task and current_task.messages:
            for msg in current_task.messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        return messages
    
    def assemble_context_for_api(self, current_task_path: str, max_tokens: int = 8000) -> List[Dict[str, str]]:
        """Assemble context and truncate for API calls"""
        messages = self.assemble_context(current_task_path)
        
        # Rough token estimation and truncation
        total_chars = sum(len(msg["content"]) for msg in messages)
        max_chars = max_tokens * 4  # ~4 chars per token
        
        # Keep all messages but prioritize recent ones if truncation needed
        if total_chars <= max_chars:
            return messages
        
        # Truncate from the beginning, keeping recent messages
        truncated_messages = []
        current_chars = 0
        
        for msg in reversed(messages):
            msg_chars = len(msg["content"])
            if current_chars + msg_chars <= max_chars:
                truncated_messages.insert(0, msg)
                current_chars += msg_chars
            else:
                break
        
        return truncated_messages

class THCFRuntime:
    """Main THCF (Task Hierarchy Context Format) system orchestrator"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.storage = THCFStorage(f"thcf_{user_id}.db")
        self.compressor = THCFCompressor()
        self.context_manager = THCFContextManager(self.storage)
        self.current_task_path = f"/{user_id}/current_conversation"
        
        # Background task queue for async compression
        self.compression_queue = asyncio.Queue()
        self.background_task = None
    
    def start_task(self, task_name: str, parent_path: Optional[str] = None) -> str:
        """Start a new task"""
        if parent_path is None:
            parent_path = f"/{self.user_id}"
        
        task_path = f"{parent_path.rstrip('/')}/{task_name}"
        
        # Create new task
        task = TaskNode(
            name=task_name,
            path=task_path,
            messages=[],
            is_active=True
        )
        
        self.storage.save_task(task)
        self.current_task_path = task_path
        
        return task_path
    
    async def end_task(self, task_path: Optional[str] = None):
        """End a task and trigger hierarchical summarization"""
        if task_path is None:
            task_path = self.current_task_path
        
        task = self.storage.load_task(task_path)
        if not task:
            return
        
        # Mark as inactive
        task.is_active = False
        task.last_modified = datetime.now()
        
        # Get compressed messages from all completed child tasks
        child_paths = self.storage.get_child_tasks(task_path)
        child_compressions = []
        
        for child_path in child_paths:
            child_task = self.storage.load_task(child_path)
            if child_task and not child_task.is_active and child_task.compressed_messages:
                child_compressions.append(child_task.compressed_messages)
        
        # Queue for hierarchical compression if it has content
        if task.messages or child_compressions:
            # Store child compressions with the task for the background processor
            task.child_compressions = child_compressions
            await self.compression_queue.put(task)
        
        self.storage.save_task(task)
        
        # Trigger parent re-compression if this task completion affects it
        parent_path = "/".join(task_path.rstrip('/').split('/')[:-1])
        if parent_path and parent_path != task_path:
            parent_task = self.storage.load_task(parent_path)
            if parent_task and not parent_task.is_active:
                # Parent is also completed, re-compress it with this new child compression
                await self.end_task(parent_path)
    
    def add_message(self, content: str, role: str, task_path: Optional[str] = None):
        """Add a message to the current task"""
        if task_path is None:
            task_path = self.current_task_path
        
        # Load or create task
        task = self.storage.load_task(task_path)
        if not task:
            # Create default task
            task_name = task_path.split('/')[-1]
            task = TaskNode(
                name=task_name,
                path=task_path,
                messages=[],
                is_active=True
            )
        
        # Add message
        message = Message(
            content=content,
            role=role,
            timestamp=datetime.now()
        )
        
        task.messages.append(message)
        task.last_modified = datetime.now()
        
        self.storage.save_task(task)
    
    @property
    def context(self) -> List[Dict[str, str]]:
        """Get assembled context as message list for LLM API"""
        return self.context_manager.assemble_context_for_api(self.current_task_path)
    
    async def process_compression_queue(self):
        """Background worker to process hierarchical compression queue"""
        while True:
            try:
                task = await self.compression_queue.get()
                
                # Get child compressions (if any)
                child_compressions = getattr(task, 'child_compressions', [])
                
                # Generate hierarchical compression
                compressed_messages = await self.compressor.compress_task_with_children(task, child_compressions)
                
                # Calculate content hash for caching
                content_to_hash = {
                    'messages': [asdict(msg) for msg in task.messages],
                    'child_compressions': child_compressions
                }
                content_hash = hashlib.md5(
                    json.dumps(content_to_hash, sort_keys=True).encode()
                ).hexdigest()
                
                # Update task with hierarchical compression
                task.compressed_messages = compressed_messages
                task.compression_hash = content_hash
                
                self.storage.save_task(task)
                
                self.compression_queue.task_done()
                
            except Exception as e:
                print(f"Error processing compression: {e}")
                await asyncio.sleep(1)

# Example usage
async def main():
    runtime = THCFRuntime("user_123")
    
    # Start background compression
    runtime.background_task = asyncio.create_task(runtime.process_compression_queue())
    
    # Start a Spanish learning task
    spanish_path = runtime.start_task("spanish_learning")
    
    # Add some conversation
    runtime.add_message("I want to learn Spanish", "user")
    runtime.add_message("Great! Let's start with basic greetings.", "assistant")
    
    # Start a subtask
    grammar_path = runtime.start_task("grammar_basics", spanish_path)
    runtime.add_message("Can you explain verb conjugations?", "user")
    runtime.add_message("Sure! In Spanish, verbs change based on who performs the action...", "assistant")
    
    # End the grammar task (triggers summarization)
    await runtime.end_task(grammar_path)
    
    # Get context for next LLM call - now returns proper message format
    messages = runtime.context
    
    # This is what you'd send to OpenAI API
    print("Messages for LLM API:")
    for msg in messages:
        print(f"{msg['role']}: {msg['content']}")
    
    # Make actual API call
    # client = openai.OpenAI(api_key="your-api-key")
    # response = client.chat.completions.create(
    #     model="gpt-4",
    #     messages=messages + [{"role": "user", "content": "What should we learn next?"}]
    # )
    
    # Add response back to current task
    doda = "Based on your progress, we should focus on conversational practice next."
    runtime.add_message(doda, "assistant")

if __name__ == "__main__":
    asyncio.run(main())
