#!/usr/bin/env python3
"""
Clean Memory Function Test - IDE Compatible
"""

import sys
import os
from pathlib import Path

# Add server to path for imports
project_root = Path(__file__).parent
server_path = project_root / 'server'
sys.path.insert(0, str(server_path))

# Change to server directory for relative paths to work
os.chdir(server_path)

from memory.memtools import get_core_memory, memory_search

def test_memory_functions():
    """Test memory functions with clean imports."""
    print("Testing Memory Functions (Clean)")
    print("=" * 32)
    
    # Test core memory
    print("1. Testing get_core_memory...")
    try:
        result = get_core_memory()
        print(f"   SUCCESS: {len(result)} chars returned")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test memory search
    print("2. Testing memory_search...")
    try:
        result = memory_search("test query", top_n=1)
        print(f"   SUCCESS: {len(result)} chars returned")
    except Exception as e:
        print(f"   ERROR: {e}")

if __name__ == "__main__":
    test_memory_functions()