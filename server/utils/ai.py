import os
import requests
import json
from typing import List, Dict, Optional, Iterator, Union

# =============================================================================
# OLLAMA PERFORMANCE OPTIMIZATIONS 
# =============================================================================

# Set optimal Ollama environment variables for consistent performance
os.environ['OLLAMA_FLASH_ATTENTION'] = '1'           # Enable flash attention
os.environ['OLLAMA_KV_CACHE_TYPE'] = 'f16'          # Full precision KV cache  
os.environ['OLLAMA_NUM_PARALLEL'] = '2'             # Parallel requests
os.environ['OLLAMA_MAX_LOADED_MODELS'] = '2'        # Allow multiple models
os.environ['OLLAMA_KEEP_ALIVE'] = '10m'             # Keep models loaded

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: dotenv not installed, environment variables will not be loaded.")

_llama_models = {}

class LLM:
    """
    A unified class for interacting with various large language models.
    """
    def __init__(self, model: str, tools: Optional[List[Dict]] = None, max_tokens: int = 2048, temperature: float = 0.7, think_level: Optional[str] = None):
        print(f"[AI DEBUG] Initializing LLM with model: {model}")
        
        if "/" not in model:
            raise ValueError("Model format must be 'provider/model_name'")
        
        # Split on first slash to get provider
        self.provider, model_path = model.split("/", 1)
        
        # Special handling for Ollama models - preserve the full model path
        if self.provider == "ollama":
            # For Ollama, the model_path can contain additional slashes (e.g., hf.co/subsectmusic/model:tag)
            # We need to preserve the full model path as Ollama expects it
            self.model_name = model_path
        else:
            # For other providers, use the original split
            self.model_name = model_path
        
        print(f"[AI DEBUG] Provider: {self.provider}, Model: {self.model_name}")
        
        self.tools = tools
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.think_level = think_level  # Support for thinking models like deepseek-r1
        self._is_thinking = False
        
        print(f"[AI DEBUG] LLM initialized successfully")
        print(f"[AI DEBUG] Tools: {len(tools) if tools else 0}")
        print(f"[AI DEBUG] Max tokens: {max_tokens}")

    def query(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Union[str, dict]]]:
        """
        Query the language model with a list of messages.
        This method streams responses, yielding chunks of different types.
        """
        print(f"[AI DEBUG] Query called with {len(messages)} messages")
        print(f"[AI DEBUG] Provider: {self.provider}")

        provider_map = {
            "ollama": self._query_ollama,
            "llama-cpp": self._query_llama_cpp,
            "openrouter": self._query_openrouter,
            "kobold-cpp": self._query_kobold,
            "lmstudio": self._query_lmstudio
        }

        if self.provider not in provider_map:
            error_msg = f"Unsupported provider: {self.provider}"
            print(f"[AI DEBUG] ERROR: {error_msg}")
            raise ValueError(error_msg)

        query_func = provider_map[self.provider]
        
        try:
            yield from self._stream_wrapper(query_func, messages)
        except Exception as e:
            print(f"[AI DEBUG] Exception in query: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _stream_wrapper(self, query_function, messages):
        """Wraps a query function with proper streaming - no unnecessary threading."""
        try:
            for chunk in query_function(messages):
                yield chunk
        except Exception as e:
            print(f"[AI DEBUG] Error in query function: {e}")
            yield {"type": "error", "delta": str(e)}

    def _process_chunk(self, content: Optional[str]) -> Iterator[Dict[str, Union[str, dict]]]:
        """
        Processes a chunk of text, handling <think> tags.
        """
        # print(f"[AI DEBUG] Processing chunk: {content[:50] if content else 'None'}...")
        
        if content is None:
            return

        while content:
            if not self._is_thinking:
                think_start = content.find("<think>")
                if think_start != -1:
                    # Yield content before the think tag
                    if think_start > 0:
                        yield {"type": "content", "delta": content[:think_start]}
                    content = content[think_start + len("<think>"):]
                    self._is_thinking = True
                else:
                    yield {"type": "content", "delta": content}
                    content = ""
            else: # We are in "thinking" mode
                think_end = content.find("</think>")
                if think_end != -1:
                    # Yield thinking content
                    if think_end > 0:
                        yield {"type": "thinking", "delta": content[:think_end]}
                    content = content[think_end + len("</think>"):]
                    self._is_thinking = False
                else:
                    yield {"type": "thinking", "delta": content}
                    content = ""

    def _query_ollama(self, messages: List[Dict[str, str]]) -> Iterator[Dict]:
        print("[AI DEBUG] Starting Ollama query...")
        
        try:
            from ollama import chat
            print("[AI DEBUG] Ollama import successful")
        except ImportError as e:
            error_msg = "Ollama is not installed. Please run 'pip install ollama'."
            print(f"[AI DEBUG] Import error: {error_msg}")
            raise ImportError(error_msg)

        params = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            }
        }
        
        # Add thinking support for compatible models 
        if hasattr(self, 'think_level') and self.think_level:
            params["think"] = self.think_level
        if self.tools:
            params["tools"] = self.tools

        print(f"[AI DEBUG] Ollama params: {params}")
        
        try:
            print("[AI DEBUG] Calling ollama.chat...")
            response_stream = chat(**params)
            print("[AI DEBUG] Got response stream from Ollama")
            
            for chunk in response_stream:
                if "message" in chunk:
                    content = chunk["message"].get("content")
                    tool_calls = chunk["message"].get("tool_calls")

                    if content:
                        # Process content directly without character splitting (original behavior)
                        yield {"type": "content", "delta": content}
                    
                    if tool_calls:
                        for tool_call in tool_calls:
                            yield {"type": "tool_call", "delta": tool_call}
            
        except Exception as e:
            print(f"[AI DEBUG] Error in Ollama query: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _query_llama_cpp(self, messages: List[Dict[str, str]]) -> Iterator[Dict]:
        print("[AI DEBUG] Starting llama-cpp query...")
        
        try:
            from llama_cpp import Llama
            print("[AI DEBUG] llama-cpp import successful")
        except ImportError:
            error_msg = "llama-cpp-python is not installed. Please run 'pip install llama-cpp-python'."
            print(f"[AI DEBUG] Error: {error_msg}")
            raise ImportError(error_msg)

        if self.tools:
            error_msg = "llama-cpp does not support tools. Use OpenRouter or Ollama."
            print(f"[AI DEBUG] Error: {error_msg}")
            raise ValueError(error_msg)

        if self.model_name not in _llama_models:
            print(f"[AI DEBUG] Loading llama-cpp model: {self.model_name}")
            _llama_models[self.model_name] = Llama(model_path=self.model_name, verbose=False, n_ctx=2048)
        
        llm = _llama_models[self.model_name]
        print("[AI DEBUG] Got llama-cpp model instance")
        
        try:
            print("[AI DEBUG] Calling llama-cpp stream...")
            stream_resp = llm(
                messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
                echo=False
            )
            
            for chunk in stream_resp:
                if "choices" in chunk and chunk["choices"]:
                    content = chunk["choices"][0].get("text")
                    if content:
                        yield from self._process_chunk(content)
            
        except Exception as e:
            print(f"[AI DEBUG] Error in llama-cpp query: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _query_openrouter(self, messages: List[Dict[str, str]]) -> Iterator[Dict]:
        print("[AI DEBUG] Starting OpenRouter query...")
        
        api_key = os.getenv("OPENROUTER_KEY")
        if not api_key:
            error_msg = "OPENROUTER_KEY environment variable not set."
            print(f"[AI DEBUG] Error: {error_msg}")
            raise KeyError(error_msg)
        
        print(f"[AI DEBUG] OpenRouter API key found: {api_key[:10]}...")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True
        }
        if self.tools:
            payload["tools"] = self.tools

        print(f"[AI DEBUG] OpenRouter payload: {payload}")

        try:
            print("[AI DEBUG] Making request to OpenRouter...")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            print(f"[AI DEBUG] OpenRouter response status: {response.status_code}")
            
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                tool_calls = delta.get("tool_calls")
                                
                                if content:
                                    yield from self._process_chunk(content)
                                
                                if tool_calls:
                                    for tool_call in tool_calls:
                                        yield {"type": "tool_call", "delta": tool_call}
                        except json.JSONDecodeError as e:
                            print(f"[AI DEBUG] JSON decode error: {e}")
                            continue
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}"
            print(f"[AI DEBUG] {error_msg}")
            if e.response.status_code == 429:
                yield {"type": "error", "delta": "Rate limit exceeded."}
            else:
                yield {"type": "error", "delta": error_msg}
        except Exception as e:
            error_msg = f"OpenRouter unexpected error: {e}"
            print(f"[AI DEBUG] {error_msg}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "delta": error_msg}

    def _query_lmstudio(self, messages: List[Dict[str, str]]) -> Iterator[Dict]:
        print("[AI DEBUG] Starting LM Studio query...")
        
        # Get LM Studio server URL from environment or use default
        lmstudio_url = os.getenv("LMSTUDIO_URL", "http://127.0.0.1:1234")
        api_endpoint = f"{lmstudio_url}/v1/chat/completions"
        
        print(f"[AI DEBUG] LM Studio URL: {lmstudio_url}")

        headers = {
            "Content-Type": "application/json"
        }
        
        # LM Studio uses OpenAI-compatible format
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True
        }
        
        # LM Studio has excellent tool support
        if self.tools:
            payload["tools"] = self.tools
            print(f"[AI DEBUG] Added {len(self.tools)} tools to LM Studio request")

        print(f"[AI DEBUG] LM Studio payload: {payload}")

        try:
            print("[AI DEBUG] Making request to LM Studio...")
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            print(f"[AI DEBUG] LM Studio response status: {response.status_code}")
            
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                tool_calls = delta.get("tool_calls")
                                
                                if content:
                                    yield from self._process_chunk(content)
                                
                                if tool_calls:
                                    for tool_call in tool_calls:
                                        yield {"type": "tool_call", "delta": tool_call}
                                        
                        except json.JSONDecodeError as e:
                            print(f"[AI DEBUG] JSON decode error: {e}")
                            continue
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"LM Studio HTTP error: {e.response.status_code} - {e.response.text}"
            print(f"[AI DEBUG] {error_msg}")
            if e.response.status_code == 404:
                yield {"type": "error", "delta": "LM Studio server not found. Make sure LM Studio is running with server enabled."}
            elif e.response.status_code == 422:
                yield {"type": "error", "delta": "Invalid request format. Check model name and parameters."}
            else:
                yield {"type": "error", "delta": error_msg}
        except requests.exceptions.ConnectionError:
            error_msg = "Cannot connect to LM Studio. Make sure LM Studio is running and the server is enabled."
            print(f"[AI DEBUG] {error_msg}")
            yield {"type": "error", "delta": error_msg}
        except Exception as e:
            error_msg = f"LM Studio unexpected error: {e}"
            print(f"[AI DEBUG] {error_msg}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "delta": error_msg}

    def _query_kobold(self, messages: List[Dict[str, str]]) -> Iterator[Dict]:
        print("[AI DEBUG] Starting Kobold.cpp query...")
        
        # Get Kobold.cpp server URL from environment or use default
        kobold_url = os.getenv("KOBOLD_URL", "http://127.0.0.1:5001")
        api_endpoint = f"{kobold_url}/v1/chat/completions"
        
        print(f"[AI DEBUG] Kobold.cpp URL: {kobold_url}")

        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,  # This can be any string for kobold.cpp
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True
        }
        
        # Note: Kobold.cpp has limited/experimental tool support
        if self.tools:
            payload["tools"] = self.tools
            print("[AI DEBUG] Warning: Kobold.cpp tool support is experimental and works best with larger models")

        print(f"[AI DEBUG] Kobold.cpp payload: {payload}")

        try:
            print("[AI DEBUG] Making request to Kobold.cpp...")
            response = requests.post(
                api_endpoint,
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            print(f"[AI DEBUG] Kobold.cpp response status: {response.status_code}")
            
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                
                                if content:
                                    yield from self._process_chunk(content)
                                    
                        except json.JSONDecodeError as e:
                            print(f"[AI DEBUG] JSON decode error: {e}")
                            continue
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"Kobold.cpp HTTP error: {e.response.status_code} - {e.response.text}"
            print(f"[AI DEBUG] {error_msg}")
            yield {"type": "error", "delta": error_msg}
        except Exception as e:
            error_msg = f"Kobold.cpp unexpected error: {e}"
            print(f"[AI DEBUG] {error_msg}")
            import traceback
            traceback.print_exc()
            yield {"type": "error", "delta": error_msg}


def embed(model: str, message: str) -> list[float]:
    """
    Simple unified embedding interface.
    """
    print(f"[AI DEBUG] Embed called with model: {model}")
    
    if "/" not in model:
        raise ValueError("Model format: 'provider/model'")
    
    # Split on first slash to get provider
    provider, model_path = model.split("/", 1)
    
    if provider == "ollama":
        try:
            import ollama
        except ImportError:
            raise ImportError("Install Ollama: pip install ollama")
        # For Ollama, use the full model path (e.g., hf.co/subsectmusic/model:tag)
        result = ollama.embeddings(model=model_path, prompt=message)
        return result["embedding"]
    
    elif provider == "llama-cpp":
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("Install llama-cpp-python: pip install llama-cpp-python")
        if model_path not in _llama_models:
            print(f"Loading model: {model_path}")
            _llama_models[model_path] = Llama(model_path=model_path, verbose=False, n_ctx=2048)
        llm = _llama_models[model_path]
        return llm.embed(message)
        
    else:
        raise ValueError(f"Unsupported provider for embeddings: {provider}")
    



"""
# Test the LLM class directly
if __name__ == "__main__":
    print("[AI DEBUG] Testing LLM class directly...")
    
    # Test with a simple model (change this to match your config)
    test_model = "ollama/qwen3:4b"  # Change this to your actual model
    
    try:
        print(f"[AI DEBUG] Creating LLM with model: {test_model}")
        llm = LLM(model=test_model, max_tokens=1000)
        print("[AI DEBUG] LLM created successfully")
        
        test_messages = [{"role": "user", "content": "Hello, how are you?"}]
        print(f"[AI DEBUG] Testing query with messages: {test_messages}")
        
        for chunk in llm.query(test_messages):
            a = chunk['delta']
            print(a, flush=True, end='')  # Print chunk directly to stdout
            
    except Exception as e:
        print(f"[AI DEBUG] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        """
