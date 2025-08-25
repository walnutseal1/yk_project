# Sleep Agent Integration Guide

This document explains how the Sleep Time Agent integrates with the main chat system and how to use them together effectively.

## Overview

The Sleep Time Agent is a background memory processing system that works alongside the main AI chat system. It processes conversations and updates memory when the main AI is idle, ensuring continuous memory improvement without interfering with real-time chat.

## Architecture

### Components

1. **Main AI System** (`server/main.py`)
   - Handles real-time chat interactions
   - Manages conversation context
   - Triggers sleep agent when appropriate

2. **Sleep Time Agent** (`server/sleep_time/sleeper_agent.py`)
   - Runs in background threads
   - Processes memory tasks when main AI is idle
   - Updates core and vector memory

3. **Memory System** (`server/memory/memtools.py`)
   - Core memory blocks (limited size, always in context)
   - Vector memory (large storage, retrieved as needed)
   - Recall memory (conversation history)

4. **Client GUI** (`client/main_gui.py`)
   - Displays sleep agent status
   - Provides manual trigger controls
   - Shows real-time integration status

## Integration Points

### 1. Memory Tool Sharing

Both the main AI and sleep agent now have access to the same comprehensive memory tools:

```python
# In server/main.py - initialize_ai_system()
handler.register_tool(mem.memory_search)
handler.register_tool(mem.vector_get)
handler.register_tool(mem.vector_memory_edit)
handler.register_tool(mem.core_memory_edit)
```

### 2. Context Sharing

The main AI provides enhanced context to the sleep agent:

```python
# Enhanced context includes messages and current core memory
enhanced_context = {
    'messages': last_n_messages,
    'core_memory': current_core_memory,
    'timestamp': datetime.now().isoformat()
}
sleep_agent.go(enhanced_context)
```

### 3. State Coordination

The sleep agent pauses when the main AI is active:

```python
def notify_main_ai_start(self):
    self.main_ai_active = True
    # Sleep agent pauses processing

def notify_main_ai_end(self):
    self.main_ai_active = False
    # Sleep agent resumes processing
```

## Configuration

### Server Configuration (`server_config.yaml`)

```yaml
# Sleep Time Agent Configs
sleep_agent_model: ollama/qwen3:4b
sleep_agent_context: 2048
sleep_agent_message_trigger: 1  # Trigger after 1 message
sleep_agent_prompt_path: prompts/sleep_agent_prompt.txt
min_sleep_interval: 30
max_sleep_interval: 300
pause_delay_after_main: 15
```

### Key Settings

- **`sleep_agent_message_trigger`**: Number of messages before auto-triggering
- **`min_sleep_interval`**: Minimum time between sleep agent cycles
- **`max_sleep_interval`**: Maximum time between cycles when idle
- **`pause_delay_after_main`**: How long to wait after main AI finishes

## API Endpoints

### Sleep Agent Status
```
GET /sleep_agent/status
```
Returns current sleep agent state, queue size, and activity status.

### Manual Trigger
```
POST /sleep_agent/trigger
Body: {"force": true}
```
Manually triggers the sleep agent to process current context.

### Health Check
```
GET /health
```
Includes sleep agent status in the health response.

### Model Management
```
POST /set_sleep_model
Body: {"model": "ollama/model-name"}
```
Changes the model used by the sleep agent.

## Usage Patterns

### 1. Automatic Processing

The sleep agent automatically processes conversations when:
- `sleep_agent_message_trigger` messages have been exchanged
- The main AI finishes processing
- Context is trimmed from memory

### 2. Manual Triggering

Use the manual trigger for:
- Testing the sleep agent
- Processing specific conversations
- Forcing memory updates

### 3. Monitoring

Monitor sleep agent activity through:
- Server console logs
- GUI status display
- API endpoints
- Health check responses

## Client GUI Integration

### Status Display

The GUI shows real-time sleep agent status:
- **Green**: Idle/Active
- **Yellow**: Processing
- **Orange**: Paused
- **Gray**: Not initialized

### Controls

- **Trigger Button**: Manually trigger sleep agent
- **Status Label**: Shows current state and queue size
- **Auto-refresh**: Updates every 10 seconds

## Memory Processing Workflow

### 1. Conversation Trigger
```
User sends message → Main AI processes → Context updated → Sleep agent notified
```

### 2. Sleep Agent Processing
```
Sleep agent receives context → Processes with LLM → Calls memory tools → Updates memory
```

### 3. Memory Integration
```
Memory updated → Available to main AI → Improved context for future conversations
```

## Best Practices

### 1. Model Selection

- Use lightweight models for sleep agent (e.g., `qwen3:4b`)
- Reserve powerful models for main AI interactions
- Consider model compatibility with your prompt format

### 2. Trigger Frequency

- Set `sleep_agent_message_trigger` based on conversation length
- Too frequent: May interfere with real-time chat
- Too infrequent: Memory updates become stale

### 3. Memory Management

- Keep core memory blocks focused and concise
- Use vector memory for detailed information
- Regularly review and clean up old memories

## Troubleshooting

### Common Issues

1. **Sleep agent not initializing**
   - Check configuration file paths
   - Verify model availability
   - Check server logs for errors

2. **Memory not updating**
   - Verify sleep agent is running
   - Check tool registration
   - Monitor sleep agent logs

3. **Performance issues**
   - Adjust sleep intervals
   - Reduce context size
   - Use lighter models

### Debug Commands

```bash
# Check sleep agent status
curl http://localhost:5000/sleep_agent/status

# Manually trigger processing
curl -X POST http://localhost:5000/sleep_agent/trigger \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

# Check health with sleep agent info
curl http://localhost:5000/health
```

## Testing

Use the provided test script to verify integration:

```bash
python test_sleep_integration.py
```

This will test:
- Backend connectivity
- Sleep agent initialization
- Message processing
- Memory updates
- API endpoints

## Future Enhancements

1. **Real-time notifications**: WebSocket updates for sleep agent status
2. **Memory analytics**: Track memory improvement over time
3. **Adaptive triggering**: Smart triggering based on conversation complexity
4. **Batch processing**: Process multiple conversations together
5. **Memory validation**: Verify memory quality and relevance

## Conclusion

The sleep agent integration provides a robust foundation for continuous memory improvement while maintaining responsive chat interactions. The system automatically balances real-time performance with background memory processing, creating a more intelligent and context-aware AI assistant.
