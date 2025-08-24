import asyncio
import aiohttp
import json
import time
import os
import psutil
from typing import List, Dict, Optional, AsyncIterator, Union, Any
from cachetools import TTLCache
from asyncio_throttle import Throttler
import hashlib

# =============================================================================
# OLLAMA PERFORMANCE OPTIMIZATIONS (from Discord bot)
# =============================================================================

# Set optimal Ollama environment variables
os.environ['OLLAMA_FLASH_ATTENTION'] = '1'           # Enable flash attention
os.environ['OLLAMA_KV_CACHE_TYPE'] = 'f16'          # Full precision KV cache
os.environ['OLLAMA_NUM_PARALLEL'] = '2'             # Parallel requests
os.environ['OLLAMA_MAX_LOADED_MODELS'] = '2'        # Allow multiple models
os.environ['OLLAMA_KEEP_ALIVE'] = '10m'             # Keep models loaded
os.environ['OLLAMA_HOST'] = '0.0.0.0:11434'        # Bind to all interfaces

class PerformanceMonitor:
    """Monitor system performance for dynamic optimization."""
    
    def __init__(self):
        self.gpu_available = self._check_gpu()
        
    def _check_gpu(self) -> bool:
        """Check if GPU is available."""
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            return len(gpus) > 0
        except:
            return False
    
    def get_system_stats(self) -> Dict:
        """Get current system performance stats."""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': psutil.virtual_memory().percent,
                'gpu_memory_percent': self._get_gpu_memory() if self.gpu_available else 0
            }
        except:
            return {'cpu_percent': 50, 'memory_percent': 50, 'gpu_memory_percent': 0}
    
    def _get_gpu_memory(self) -> float:
        """Get GPU memory usage percentage."""
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            return gpus[0].memoryUtil * 100 if gpus else 0
        except:
            return 0

class AsyncOllamaClient:
    """
    BLAZING FAST async Ollama client with advanced optimizations.
    Based on optimized Discord bot implementation.
    """
    
    def __init__(self, 
                 base_url: str = "http://localhost:11434",
                 max_connections: int = 10,
                 requests_per_second: int = 8,
                 cache_ttl: int = 600,
                 cache_maxsize: int = 1000):
        
        self.base_url = base_url.rstrip('/')
        self.max_connections = max_connections
        self.requests_per_second = requests_per_second
        
        # Performance monitoring and optimization
        self.performance_monitor = PerformanceMonitor()
        self.model_cache = {}  # Track loaded models
        self.active_requests = 0
        self.max_concurrent = 4
        
        # Connection pool and throttling
        self._connector = None
        self._session = None
        self._throttler = Throttler(rate_limit=requests_per_second)
        
        # Enhanced KV Cache for repeated queries
        self._cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)
        self._model_cache = {}  # Per-model caching
        
        # Connection pool management
        self._connection_pool_lock = asyncio.Lock()
        self._is_initialized = False
        
        # Advanced request queue for load balancing
        self._request_queue = asyncio.Queue()
        self._priority_queue = asyncio.PriorityQueue()  # For priority requests
        self._workers = []
        self._worker_count = min(max_connections, 4)
        
    async def __aenter__(self):
        await self._initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def _initialize(self):
        """Initialize connection pool and worker tasks."""
        if self._is_initialized:
            return
            
        async with self._connection_pool_lock:
            if self._is_initialized:
                return
                
            # Create connector with connection pooling
            self._connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=self.max_connections,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            # Create session with connection pool
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            
            # Start worker tasks for request processing
            for i in range(self._worker_count):
                worker = asyncio.create_task(self._request_worker(f"worker-{i}"))
                self._workers.append(worker)
                
            self._is_initialized = True
            
    async def close(self):
        """Clean shutdown of connection pool and workers."""
        if not self._is_initialized:
            return
            
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
            
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        # Close session and connector
        if self._session:
            await self._session.close()
        if self._connector:
            await self._connector.close()
            
        self._is_initialized = False
        
    def format_messages_for_bpe(self, messages: List[Dict]) -> List[Dict]:
        """Format messages with proper BPE tags for optimal tokenization."""
        formatted = []
        for msg in messages:
            content = msg.get('content', '')
            
            # Add BPE formatting for better tokenization
            if msg.get('role') == 'system':
                content = f"<|system|>\n{content}\n<|/system|>"
            elif msg.get('role') == 'user':
                content = f"<|user|>\n{content}\n<|/user|>"
            elif msg.get('role') == 'assistant':
                content = f"<|assistant|>\n{content}\n<|/assistant|>"
            elif msg.get('role') == 'tool':
                content = f"<|tool|>\n{content}\n<|/tool|>"
                
            formatted_msg = msg.copy()
            formatted_msg['content'] = content
            formatted.append(formatted_msg)
            
        return formatted
    
    def _generate_cache_key(self, model: str, messages: List[Dict], 
                           temperature: float, max_tokens: int) -> str:
        """Generate enhanced cache key with model-specific caching."""
        # Create model-specific cache key
        key_data = {
            "model": model,
            "messages": str(messages)[-500:],  # Use last 500 chars for context
            "temperature": round(temperature, 2),
            "max_tokens": max_tokens
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"{model}:{hashlib.sha256(key_str.encode()).hexdigest()[:16]}"
    
    async def get_performance_adjustments(self) -> Dict[str, Any]:
        """Get dynamic performance adjustments based on system load."""
        stats = self.performance_monitor.get_system_stats()
        adjustments = {}
        
        # CPU-based adjustments
        if stats['cpu_percent'] > 90:
            adjustments['reduce_threads'] = True
            adjustments['lower_batch_size'] = True
        elif stats['cpu_percent'] < 30:
            adjustments['increase_parallel'] = True
            
        # Memory-based adjustments  
        if stats['memory_percent'] > 90:
            adjustments['reduce_context'] = True
            adjustments['clear_cache'] = True
            
        # GPU-based adjustments
        if stats['gpu_memory_percent'] > 85:
            adjustments['reduce_gpu_layers'] = True
            
        return adjustments
        
    async def _request_worker(self, worker_name: str):
        """Worker task that processes requests from the queue."""
        print(f"[ASYNC AI] Starting worker: {worker_name}")
        
        while True:
            try:
                # Get request from queue
                request_data = await self._request_queue.get()
                
                # Process the request
                await self._process_request(request_data)
                
                # Mark task as done
                self._request_queue.task_done()
                
            except asyncio.CancelledError:
                print(f"[ASYNC AI] Worker {worker_name} cancelled")
                break
            except Exception as e:
                print(f"[ASYNC AI] Worker {worker_name} error: {e}")
                
    async def _process_request(self, request_data: Dict):
        """Process individual request with advanced optimizations."""
        # Wait for available slot (connection limiting)
        while self.active_requests >= self.max_concurrent:
            await asyncio.sleep(0.1)
        
        self.active_requests += 1
        start_time = time.time()
        
        try:
            # Apply rate limiting
            async with self._throttler:
                model = request_data["model"]
                messages = request_data["messages"] 
                temperature = request_data.get("temperature", 0.7)
                max_tokens = request_data.get("max_tokens", 2048)
                tools = request_data.get("tools")
                response_queue = request_data["response_queue"]
                
                # Check enhanced cache first
                cache_key = self._generate_cache_key(model, messages, temperature, max_tokens)
                cached_response = self._cache.get(cache_key)
                
                if cached_response:
                    print("[ASYNC AI] ⚡ Cache hit!")
                    for chunk in cached_response:
                        await response_queue.put(chunk)
                    await response_queue.put(None)  # Signal completion
                    return
                
                # Format messages with BPE tags
                formatted_messages = self.format_messages_for_bpe(messages)
                
                # Get system stats for dynamic optimization
                stats = self.performance_monitor.get_system_stats()
                
                # Build optimized payload with performance settings
                options = {
                    'num_ctx': 8192,  # Large context
                    'temperature': temperature,
                    'top_p': 0.9,
                    'repeat_penalty': 1.1,
                    'num_predict': max_tokens,
                    'num_batch': 128,  # Batch size optimization
                    'num_thread': min(8, psutil.cpu_count()),
                    'num_gpu_layers': -1 if self.performance_monitor.gpu_available else 0,
                    # Advanced optimizations
                    'use_mmap': True,
                    'use_mlock': True,
                    'flash_attn': True,
                }
                
                # Dynamic performance adjustments
                if stats['cpu_percent'] > 80:
                    options['num_thread'] = max(2, options['num_thread'] // 2)
                if stats['memory_percent'] > 85:
                    options['num_ctx'] = min(4096, options['num_ctx'])
                
                payload = {
                    "model": model,
                    "messages": formatted_messages,
                    "stream": True,
                    "options": options
                }
                
                if tools:
                    payload["tools"] = tools
                
                # Store response chunks for caching
                response_chunks = []
                
                async with self._session.post(f"{self.base_url}/api/chat", 
                                            json=payload) as response:
                    response.raise_for_status()
                    
                    async for line in response.content:
                        if line:
                            try:
                                data = json.loads(line.decode('utf-8'))
                                
                                # Process chunk
                                chunk = self._process_ollama_chunk(data)
                                if chunk:
                                    response_chunks.append(chunk)
                                    await response_queue.put(chunk)
                                    
                            except json.JSONDecodeError:
                                continue
                                
                # Cache the response
                if response_chunks:
                    self._cache[cache_key] = response_chunks
                    
                # Signal completion
                await response_queue.put(None)
                
        except Exception as e:
            print(f"[ASYNC AI] ❌ Request failed: {e}")
            await response_queue.put({"type": "error", "delta": str(e)})
            await response_queue.put(None)
        finally:
            self.active_requests -= 1
            # Log performance metrics
            duration = time.time() - start_time
            print(f"[ASYNC AI] ⏱️ Request completed in {duration:.2f}s")
            
    def _process_ollama_chunk(self, data: Dict) -> Optional[Dict]:
        """Process individual Ollama response chunk."""
        if "message" in data:
            content = data["message"].get("content")
            tool_calls = data["message"].get("tool_calls")
            
            if content:
                return {"type": "content", "delta": content}
            elif tool_calls:
                return {"type": "tool_call", "delta": tool_calls[0]}
                
        return None
        
    async def chat_stream(self, 
                         model: str,
                         messages: List[Dict[str, str]], 
                         temperature: float = 0.7,
                         max_tokens: int = 2048,
                         tools: Optional[List[Dict]] = None) -> AsyncIterator[Dict]:
        """
        Stream chat completion with async processing.
        
        Args:
            model: Ollama model name
            messages: Chat messages
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            tools: Function calling tools
            
        Yields:
            Dict: Response chunks
        """
        await self._initialize()
        
        # Create response queue for this request
        response_queue = asyncio.Queue()
        
        # Queue the request for processing
        request_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
            "response_queue": response_queue
        }
        
        await self._request_queue.put(request_data)
        
        # Stream responses
        while True:
            chunk = await response_queue.get()
            if chunk is None:  # End signal
                break
            yield chunk


class AsyncLLM:
    """
    Async version of LLM class with high-performance optimizations.
    """
    
    def __init__(self, 
                 model: str, 
                 tools: Optional[List[Dict]] = None, 
                 max_tokens: int = 2048, 
                 temperature: float = 0.7,
                 max_concurrent_requests: int = 5):
        
        if "/" not in model:
            raise ValueError("Model format must be 'provider/model_name'")
            
        self.provider, self.model_name = model.split("/", 1)
        self.tools = tools
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Initialize provider-specific clients
        self._clients = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def close(self):
        """Close all provider clients."""
        for client in self._clients.values():
            if hasattr(client, 'close'):
                await client.close()
                
    async def _get_ollama_client(self) -> AsyncOllamaClient:
        """Get or create Ollama client."""
        if 'ollama' not in self._clients:
            self._clients['ollama'] = AsyncOllamaClient(
                max_connections=10,
                requests_per_second=8,
                cache_ttl=600  # 10 minute cache
            )
        return self._clients['ollama']
        
    async def query(self, messages: List[Dict[str, str]]) -> AsyncIterator[Dict[str, Union[str, dict]]]:
        """
        Async query with concurrent request limiting.
        
        Args:
            messages: Chat messages
            
        Yields:
            Dict: Response chunks with type and delta
        """
        async with self._semaphore:  # Limit concurrent requests
            if self.provider == "ollama":
                client = await self._get_ollama_client()
                
                async for chunk in client.chat_stream(
                    model=self.model_name,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    tools=self.tools
                ):
                    # Process thinking tags if needed
                    if chunk.get("type") == "content":
                        for sub_chunk in self._process_chunk(chunk["delta"]):
                            yield sub_chunk
                    else:
                        yield chunk
            else:
                raise ValueError(f"Async support not implemented for provider: {self.provider}")
                
    def _process_chunk(self, content: Optional[str]) -> AsyncIterator[Dict[str, Union[str, dict]]]:
        """Process content chunks, handling <think> tags."""
        if content is None:
            return
            
        # Simple implementation - extend as needed
        yield {"type": "content", "delta": content}


# High-level async functions for easy usage
async def async_chat(model: str, 
                    messages: List[Dict[str, str]], 
                    tools: Optional[List[Dict]] = None,
                    temperature: float = 0.7,
                    max_tokens: int = 2048) -> AsyncIterator[Dict]:
    """
    High-level async chat function.
    
    Usage:
        async for chunk in async_chat("ollama/llama3", messages):
            print(chunk["delta"], end="", flush=True)
    """
    async with AsyncLLM(
        model=model, 
        tools=tools, 
        temperature=temperature, 
        max_tokens=max_tokens
    ) as llm:
        async for chunk in llm.query(messages):
            yield chunk


# Example usage and testing
async def test_async_ollama():
    """Test the async Ollama implementation."""
    print("[ASYNC AI] Testing async Ollama client...")
    
    messages = [{"role": "user", "content": "Hello! Can you count to 5?"}]
    
    async for chunk in async_chat("ollama/llama3:8b", messages):
        if chunk["type"] == "content":
            print(chunk["delta"], end="", flush=True)
        elif chunk["type"] == "error":
            print(f"\nError: {chunk['delta']}")
            
    print("\n[ASYNC AI] Test completed!")


if __name__ == "__main__":
    asyncio.run(test_async_ollama())