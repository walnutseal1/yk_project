import os
import json
import datetime
from datetime import timezone
import utils.ai as ai
import math
import sqlite3
import yaml

with open('../server_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Paths
CORE_DIR = config['core_dir']
VECTOR_DIR = config['vector_dir']
CACHE_FILE = config['cache_file']
EMBED_MODEL = config['embed_model']
#=============================================================================================================================================================================================================
# Vector Memory
#=============================================================================================================================================================================================================
def get_vector_memory_files():
    """
    Get all vector memory JSON files, excluding embedding and cache files.
    
    Returns:
        list: List of vector memory filenames (without .json extension)
    """
    filenames = []
    for filename in os.listdir(VECTOR_DIR):
        if filename.endswith('.json') and not (
            filename.endswith('.embedding.json') or filename.endswith('.cache.json')
        ):
            # Remove .json extension
            name_without_ext = filename[:-5]  # Remove last 5 characters (.json)
            filenames.append(name_without_ext)
    
    return sorted(filenames)

def load_cache() -> set:
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return set()
        try:
            return set(json.loads(content))
        except json.JSONDecodeError as e:
            print(f"[load_cache] Warning: cache file is malformed. Ignoring. Error: {e}")
            return set()

def save_cache(cache: set):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(cache)), f, indent=2)

def clear_cache(label=None, clear_all=False):
    cache = load_cache()
    if clear_all:
        cache.clear()
    elif label is not None:
        cache.discard(label)
    save_cache(cache)

def embed_all():
    """
    Embeds all vector memory blocks that aren't already cached.
    Saves embeddings to .embedding.json files and updates the cache.
    """
    cache = load_cache()
    updated_cache = set(cache)

    for fname in os.listdir(VECTOR_DIR):
        if not fname.endswith(".json") or fname.startswith("."):
            continue
        if fname.endswith(".embedding.json"):
            continue
        label = fname[:-5]
        if label in cache:
            continue  # Skip already embedded
        path = os.path.join(VECTOR_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        content = data.get("content", "").strip()
        if not content:
            continue

        embedding = ai.embed(EMBED_MODEL, content)

        emb_path = os.path.join(VECTOR_DIR, f"{label}.embedding.json")
        with open(emb_path, "w", encoding="utf-8") as f:
            json.dump(embedding, f)

        updated_cache.add(label)

    save_cache(updated_cache)
    return f"Embedding complete. {len(updated_cache - cache)} new files embedded."

def cosine_similarity(vec1, vec2):
    """
    Compute cosine similarity between two vectors.
    """
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

import os

def vector_search(query: str, top_n: int = 2, threshold: float =  0.4) -> list[dict]:
    """
    Search vector memory blocks using embeddings. Should be used sparingly, refer to the base instructions for when to use this.

    Args:
        query (str): The search query string. Do not use the users input for this.
        top_n (int): Number of top results to return. Defaults to 2, a reasonable amount.
    Returns:
        List of dictionaries: [{label, content, score}, ...]
    """
    embed_all()  # Ensure all vector files are embedded and cached

    query_embedding = ai.embed(EMBED_MODEL, query)
    results = []

    for fname in os.listdir(VECTOR_DIR):
        if not fname.endswith(".json") or fname.startswith(".") or fname.endswith(".embedding.json"):
            continue

        label = fname[:-5]
        mem_path = os.path.join(VECTOR_DIR, fname)
        emb_path = os.path.join(VECTOR_DIR, f"{label}.embedding.json")

        # Skip if no embedding
        if not os.path.exists(emb_path):
            continue

        # Load content
        with open(mem_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        content = data.get("content", "").strip()
        if not content:
            continue

        # Load embedding
        with open(emb_path, "r", encoding="utf-8") as ef:
            memory_embedding = json.load(ef)

        score = round(cosine_similarity(query_embedding, memory_embedding),5)
        if score < threshold:
            continue
        
        results.append({
            "label": label,
            "content": content,
            "score": score
        })

    # Sort by descending similarity
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]

def vector_memory_edit(label: str, new_text: str, old_text: str = "") -> str:
    """
    Create or update a vector memory block by replacing or appending text, identified by label. 

    - If old_text is provided, replaces it with new_text.
    - If old_text is empty, appends new_text to the vector memory block.
    - If the memory block doesn't exist, it creates a new one with new_text as content.
    
    Args:
        label (str): Filename without `.json`, used to locate or create the block in vector memory. Creates a new one if it doesn't exist.
        new_text (str): Text to insert or append.
        old_text (str): Text to be replaced. If empty, new_text is appended instead.
    
    Returns:
        str: Success or failure message.
    """
    filepath = os.path.join(VECTOR_DIR, f"{label}.json")

    # Create new block if it doesn't exist
    if not os.path.exists(filepath):
        data = {
            "label": label,
            "content": new_text.strip(),
            "metadata": {
                "last_updated": datetime.datetime.now(timezone.utc).isoformat() + "Z",
                "current_chars": len(new_text.strip()),
                "max_chars": 5000
            }
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return f"Success: New vector memory block '{label}' created."

    # Load existing block
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = data.get("content", "")
    if "metadata" not in data:
        data["metadata"] = {}

    if old_text:
        if old_text in content:
            content = content.replace(old_text, new_text)
        else:
            content = f"{content} {new_text}".strip()
    else:
        content = f"{content} {new_text}".strip()
    # Update metadata
    current_chars = len(content)
    max_chars = data["metadata"].get("max_chars", 5000)
    if current_chars > max_chars:
        return f"Failed: Updated content exceeds max character limit of {max_chars}."

    # Save updated block
    data["content"] = content
    data["metadata"]["last_updated"] = datetime.datetime.now(timezone.utc).isoformat() + "Z"
    data["metadata"]["current_chars"] = current_chars
    data["metadata"]["max_chars"] = max_chars

    clear_cache(label=label)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return f"Success: Vector memory block '{label}' updated."
#=============================================================================================================================================================================================================
# Core Memory
#=============================================================================================================================================================================================================
def core_memory_edit(label: str, new_text: str, old_text: str = "") -> str:
    """
    Edit the contents of a core memory block by replacing or appending text, identified by label.

    - If old_text is provided, replaces it with new_text.
    - If old_text is empty, appends new_text to the vector memory block.
    - If the memory block doesn't exist, it creates a new one with new_text as content.
    
    Args:
        label (str): Section of the memory to be edited. This corresponds to the filename (without `.json`) in the `core/` directory.
        new_text (str): Text to insert or append.
        old_text (str): Text to be replaced. If empty, new_text is appended instead.
    
    Returns:
        str: Success or failure message.
    """
    # Load existing block
    filepath = os.path.join(CORE_DIR, f"{label}.json")
    if not os.path.exists(filepath):
        return f"Failed: Core memory block '{label}' does not exist."
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("content", "")
    if "metadata" not in data:
        data["metadata"] = {}

    if old_text:
        if old_text in content:
            content = content.replace(old_text, new_text)
        else:
            content = f"{content} {new_text}".strip()
    else:
        content = f"{content} {new_text}".strip()
    # Update metadata
    current_chars = len(content)
    max_chars = data["metadata"].get("max_chars", 5000)
    if current_chars > max_chars:
        return f"Failed: Updated content exceeds max character limit of {max_chars}."
    # Save updated block
    data["content"] = content
    data["metadata"]["last_updated"] = datetime.datetime.now(timezone.utc).isoformat() + "Z"
    data["metadata"]["current_chars"] = current_chars
    data["metadata"]["max_chars"] = max_chars

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return f"Success: Vector memory block '{label}' updated."

def get_core_memory() -> str:
    """
    Reads all core memory blocks and returns a formatted string matching the requested layout.
    """

    # Get current UTC time string
    now_utc = datetime.datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%d %I:%M:%S %p UTC+0000")

    # List all core memory files
    filenames = [f for f in os.listdir(CORE_DIR) if f.endswith(".json")]

    # Track latest last_updated timestamp among blocks
    last_modified_times = []

    # Parsed memory blocks, keyed by label
    memory_blocks = {}

    for fname in filenames:
        filepath = os.path.join(CORE_DIR, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        label = data.get("label", fname[:-5])
        description = data.get("description", "No description provided.")
        content = data.get("content", "")
        metadata = data.get("metadata", {})

        last_updated_str = metadata.get("last_updated", "1970-01-01T00:00:00Z")
        try:
            last_updated_dt = datetime.datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
        except Exception:
            last_updated_dt = datetime(1970, 1, 1)

        last_modified_times.append(last_updated_dt)

        # Default metadata values for chars_current and max_chars
        chars_current = metadata.get("current_chars", len(content))
        chars_limit = metadata.get("max_chars", 5000)

        memory_blocks[label] = {
            "description": description,
            "content": content,
            "chars_current": chars_current,
            "chars_limit": chars_limit
        }
    # Determine the last modified time overall
    if last_modified_times:
        latest_mod = max(last_modified_times)
        latest_mod_str = latest_mod.strftime("%Y-%m-%d %I:%M:%S %p UTC+0000")
    else:
        latest_mod_str = "1970-01-01 12:00:00 AM UTC+0000"
    # Determine # of vector memories
    v_files = get_vector_memory_files()
    v_mems = ", ".join(v_files)
    # Compose header metadata section
    header = (
        "<memory_metadata>\n"
        f"- The current time is: {now_str}\n"
        f"- Core memory blocks last modified: {latest_mod_str}\n"
        f"- 0 previous messages between you and the user are stored in recall memory (use tools to view and access them)\n"
        f"- {len(v_files)} total memories you created are stored in vector memory. Use tools to view and access full contents.\n"
        "</memory_metadata>\n"
    )

    # Compose memory blocks section
    body_lines = ["<memory_blocks>", "The following memory blocks are currently engaged in your core memory unit:"]

    for label, block in memory_blocks.items():
        body_lines.append(f"<{label}>")
        body_lines.append("<description>")
        body_lines.append(block["description"])
        body_lines.append("</description>")
        body_lines.append("<metadata>")
        body_lines.append(f"- chars_current={block['chars_current']}")
        body_lines.append(f"- chars_limit={block['chars_limit']}")
        body_lines.append("</metadata>")
        body_lines.append("<value>")
        body_lines.append(block["content"])
        body_lines.append("</value>")
        body_lines.append(f"</{label}>")

    body_lines.append("</memory_blocks>")

    # Join everything into a single string
    return header + "\n".join(body_lines)
#=============================================================================================================================================================================================================
# Recall Memory
#=============================================================================================================================================================================================================
RECALL_DB_PATH = config.get('recall_dir')

def init_recall_db():
    """Initializes the recall database and creates the messages table if it doesn't exist."""
    with sqlite3.connect(RECALL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recalled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def append_to_recall(messages: list):
    """Appends a list of messages to the recall database."""
    with sqlite3.connect(RECALL_DB_PATH) as conn:
        cursor = conn.cursor()
        for message in messages:
            cursor.execute(
                "INSERT INTO recalled_messages (role, content) VALUES (?, ?)",
                (message.get('role'), message.get('content'))
            )
        conn.commit()

def conversation_search(query: str, n_neighbors: int = 0, limit: int = 1) -> tuple[list, list]:
    """
    Search the recall memory for past conversation snippets and their surrounding context. Only use this if the user explicitly references past conversations.

    Args:
        query (str): The text to search for in the conversation history. Do not use the users input for this.
        n_neighbors (int): The number of neighboring messages to retrieve (before and after). 
                         If odd, the extra message is taken from before the match. Defaults to 0.
        limit (int): The maximum number of primary matches to return. Defaults to 1.

    Returns:
        tuple: (snippets, match_ids) where snippets is a list of message lists and match_ids is a list of IDs
    """
    with sqlite3.connect(RECALL_DB_PATH) as conn:
        cursor = conn.cursor()
        # Find the initial matching messages
        try:
            cursor.execute(
                "SELECT id FROM recalled_messages WHERE content MATCH ? ORDER BY timestamp DESC LIMIT ?", 
                (query, limit)
            )
        except sqlite3.OperationalError:
            cursor.execute(
                "SELECT id FROM recalled_messages WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?", 
                (f'%{query}%', limit)
            )
        match_ids = [row[0] for row in cursor.fetchall()]

        # Determine the number of neighbors before and after
        after = n_neighbors // 2
        before = n_neighbors - after

        snippets = []
        for match_id in match_ids:
            start_id = max(1, match_id - before)
            end_id = match_id + after
            
            cursor.execute(
                "SELECT role, content FROM recalled_messages WHERE id BETWEEN ? AND ? ORDER BY id ASC",
                (start_id, end_id)
            )
            messages = cursor.fetchall()
            snippets.append(messages)
    return snippets, match_ids

def memory_search(query: str, n_neighbors: int = 0, top_n: int = 2, exclude: str = "") -> str:
    """
    Search the memory for information across vector and recall memory.

    Args:
        query (str): The text to search for in the conversation history. Do not use the users input for this.
        n_neighbors (int): The number of neighboring messages to retrieve (before and after). If odd, the extra message is taken from before the match. Defaults to 0.
        top_n (int): Number of top results to return. Defaults to 2, a reasonable amount.
        exclude (str): Exclude certain types of memory from the search. Defaults to "", which includes all types.
    Returns:
        str: A formatted string of matching memories, or a not found message.
    """
    use_vector = not ("vect" in exclude.lower())
    use_recall = not ("rec" in exclude.lower() or "conv" in exclude.lower())
    
    body_lines = ["<memory_search>", "Here are the results for your memory search."]
    
    # Track counts for summary
    vector_count = 0
    recall_count = 0
    
    # Vector memory search
    if use_vector:
        try:
            vector_blocks = vector_search(query, top_n)
            vector_count = len(vector_blocks)
            
            if vector_blocks:
                body_lines.append("<vector>")
                for block in vector_blocks:
                    label = block.get("label", "unknown_label")
                    content = block.get("content", "")
                    score = block.get("score", 0.0)
                    body_lines.append(f"<{label}>")
                    body_lines.append("<metadata>")
                    body_lines.append(f"- embedding score: {score}")
                    body_lines.append("</metadata>")
                    body_lines.append("<value>")
                    body_lines.append(content)
                    body_lines.append("</value>")
                    body_lines.append(f"</{label}>")
                body_lines.append("</vector>")
        except Exception as e:
            body_lines.append(f"<vector><error>Vector search failed: {e}</error></vector>")
    
    # Recall memory search
    if use_recall:
        try:
            recall_snippets, match_ids = conversation_search(query, n_neighbors, top_n)
            recall_count = len(match_ids)
            
            if recall_snippets:
                body_lines.append("<recall>")
                for snippet in recall_snippets:
                    body_lines.append("<snippet>")
                    for role, content in snippet:
                        body_lines.append(f'<message role="{role}">{content}</message>')
                    body_lines.append("</snippet>")
                body_lines.append("</recall>")
        except Exception as e:
            body_lines.append(f"<recall>\n<error>\nRecall search failed: {e}\n</error>\n</recall>")
    
    # Add summary at the end
    summary_parts = []
    if use_recall:
        summary_parts.append(f"{recall_count} recall matches")
    if use_vector:
        summary_parts.append(f"{vector_count} vector matches")

    if vector_count == 0 and recall_count == 0:
        if use_vector or use_recall:
            # Searches were performed, but no results were found
            summary = f"<summary>\nNo results found for '{query}'. The information may not be in memory, or you could try a different query.\n</summary>"
        else:
            # No searches were performed
            summary = "<summary>\nNo memory types enabled for search.\n</summary>"
    else:
        # Results were found, so create a summary of the counts
        summary = f"<summary>\nFound {', '.join(summary_parts)} for '{query}'\n</summary>"

    body_lines.insert(2, summary)
    
    body_lines.append("</memory_search>")
    
    return "\n".join(body_lines)

def vector_get(query: str, top_n: int = 2) -> str:
    """
    Search the memory for information across vector memory.

    Args:
        query (str): The text to search for in the conversation history. Do not use the users input for this.
        top_n (int): Number of top results to return. Defaults to 2, a reasonable amount.
    Returns:
        str: A formatted string of matching memories, or a not found message.
    """
    return memory_search(query, topn=top_n, exclude="recall")
