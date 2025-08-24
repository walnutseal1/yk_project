import os
import json
import yaml
with open('../server_config.yaml', 'r') as f:
    config = yaml.safe_load(f)


def count_tokens(text):
    """Estimates the number of tokens in a string."""
    return len(text) / 4

def trim_context(messages, max_tokens, system_messages: list = None):
    """
    Trims a list of messages to be under a max token limit, optionally reserving space for a system prompt.

    Args:
        messages (list): A list of message dictionaries.
        max_tokens (int): The maximum number of tokens allowed for the entire payload.
        system_messages (list, optional): A list of system message dictionaries to account for. Defaults to None.

    Returns:
        tuple: A tuple containing:
            - list: The trimmed list of messages.
            - list: The messages that were removed.
    """
    system_tokens = 0
    if system_messages:
        system_tokens = sum(count_tokens(json.dumps(m)) for m in system_messages)

    # The available token budget for the main conversation messages
    available_tokens = max_tokens - system_tokens

    total_tokens = sum(count_tokens(json.dumps(m)) for m in messages)
    trimmed_messages = []

    # Keep a copy of the original messages to pop from, so we don't modify the list passed in
    messages_copy = list(messages)

    while total_tokens > available_tokens:
        if not messages_copy:
            # This would happen if the system message alone exceeds max_tokens, or if messages is empty
            break
        # Remove the oldest message
        trimmed_message = messages_copy.pop(0)
        trimmed_messages.append(trimmed_message)
        # Recalculate the total tokens of the remaining messages
        total_tokens = sum(count_tokens(json.dumps(m)) for m in messages_copy)

    return messages_copy, trimmed_messages

def save_context(context, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(context, f, indent=4, ensure_ascii=False)

def load_context(filepath, print_messages=0):
    if not os.path.exists(filepath):
        print(f"No context file found at {filepath}")
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            messages = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return []
    if print_messages:
        recent_msgs = messages[-print_messages:]
        for msg in recent_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not role == "tool":
                print(f"{role.capitalize()}: {content}")
    return messages

    """
if __name__ == '__main__':
    # Example Usage
    sample_system_prompt = [
        {"role": "system", "content": "You are a helpful assistant. Your name is Yumeko."}
    ]
    sample_messages = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you today?"},
        {"role": "user", "content": "I want to write a story."},
        {"role": "assistant", "content": "That sounds fun! What should the story be about?"},
        {"role": "user", "content": "Let's make it a sci-fi story about a robot who discovers music."},
        {"role": "assistant", "content": "Excellent idea! Let's begin..."}
    ]

    max_token_limit = 100
    
    print("--- Example 1: Without System Prompt ---")
    print(f"Original messages: {len(sample_messages)}")
    print(f"Max token limit: {max_token_limit}")

    # Pass a copy of sample_messages to avoid modifying it in place
    final_context, removed_messages = trim_context(list(sample_messages), max_token_limit)

    print(f"Trimmed messages: {len(final_context)}")
    print(f"Removed messages: {len(removed_messages)}")
    print("----")
    print("Final context:")
    for msg in final_context:
        print(msg)
    
    print("\n--- Example 2: With System Prompt ---")
    print(f"Original messages: {len(sample_messages)}")
    print(f"Max token limit: {max_token_limit}")
    system_tokens = sum(count_tokens(json.dumps(m)) for m in sample_system_prompt)
    print(f"System prompt tokens: ~{system_tokens:.0f}")

    final_context_with_system, removed_messages_with_system = trim_context(
        list(sample_messages), 
        max_token_limit, 
        system_messages=sample_system_prompt
    )

    print(f"Trimmed messages: {len(final_context_with_system)}")
    print(f"Removed messages: {len(removed_messages_with_system)}")
    print("----")
    print("Final context (accounting for system prompt):")
    for msg in final_context_with_system:
        print(msg)
    """