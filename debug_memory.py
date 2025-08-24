#!/usr/bin/env python3
"""
Debug Memory Issues
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))

try:
    print("Testing memory module import...")
    import server.memory.memtools as mem
    print("✅ Memory module imported successfully")
    
    print(f"📊 Available functions in mem: {[x for x in dir(mem) if not x.startswith('_')]}")
    
    print("Testing get_core_memory function...")
    if hasattr(mem, 'get_core_memory'):
        print("✅ get_core_memory function exists")
        print(f"📋 Function type: {type(mem.get_core_memory)}")
        
        # Test the function
        try:
            result = mem.get_core_memory()
            print(f"✅ Function executed successfully")
            print(f"📏 Result length: {len(result)} characters")
            print(f"📄 Result preview: {result[:200]}...")
        except Exception as e:
            print(f"❌ Function execution failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("❌ get_core_memory function not found")
        
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()