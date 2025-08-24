#!/usr/bin/env python3
"""
Test Memory Functions Directly - Pinpoint the Issue
"""

import sys
import os

# Set up the path correctly for both running and IDE
project_root = os.path.dirname(os.path.abspath(__file__))
server_path = os.path.join(project_root, 'server')
sys.path.insert(0, server_path)
sys.path.insert(0, project_root)

def test_memory_imports():
    """Test memory imports to find the exact issue."""
    print("Testing Memory Module Imports")
    print("=" * 35)
    
    try:
        print("1. Testing basic import...")
        os.chdir(os.path.join(os.path.dirname(__file__), 'server'))
        
        import memory.memtools as mem
        print("   SUCCESS: memory.memtools imported")
        
        print("2. Testing get_core_memory function...")
        if hasattr(mem, 'get_core_memory'):
            print("   SUCCESS: get_core_memory exists")
            
            # Test the actual function call
            try:
                result = mem.get_core_memory()
                print(f"   SUCCESS: Function executed - {len(result)} chars returned")
            except Exception as e:
                print(f"   ERROR: Function call failed - {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   ERROR: get_core_memory not found")
            
        print("3. Testing memory_search function...")
        if hasattr(mem, 'memory_search'):
            print("   SUCCESS: memory_search exists")
            
            try:
                result = mem.memory_search("test query", top_n=1)
                print(f"   SUCCESS: memory_search executed - {len(result)} chars returned")
            except Exception as e:
                print(f"   ERROR: memory_search failed - {e}")
        else:
            print("   ERROR: memory_search not found")
            
        print("4. Checking for callable issues...")
        print(f"   mem module type: {type(mem)}")
        print(f"   get_core_memory type: {type(mem.get_core_memory) if hasattr(mem, 'get_core_memory') else 'Not found'}")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_memory_imports()