#!/usr/bin/env python3
"""
Simple Sleep-Time Agent Test - Windows Compatible
"""

import sys
import os
import time
import asyncio
from datetime import datetime

# Add server path and change to server directory
project_root = os.path.dirname(os.path.abspath(__file__))
server_path = os.path.join(project_root, 'server')
sys.path.insert(0, server_path)
os.chdir(server_path)

def test_memory_system():
    """Test memory system integration."""
    print("\nTesting Memory System...")
    print("=" * 30)
    
    try:
        import memory.memtools as mem
        
        print("Testing memory initialization...")
        mem.init_recall_db()
        print("SUCCESS: Recall database initialized")
        
        print("Testing core memory...")
        core_memory = mem.get_core_memory()
        print(f"SUCCESS: Core memory loaded ({len(core_memory)} characters)")
        
        print("Testing memory search...")
        results = mem.memory_search("test query", top_n=1)
        print(f"SUCCESS: Memory search returned {len(results)} characters")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Memory system failed - {e}")
        return False

def test_sync_sleep_agent():
    """Test the sync sleep-time agent."""
    print("\nTesting Sync Sleep Agent...")
    print("=" * 30)
    
    try:
        from sleep_time.sleeper_agent import SleepTimeAgent
        
        agent = SleepTimeAgent()
        agent.start()
        print("SUCCESS: Sync agent started")
        
        # Add a simple task
        agent.add_task("Test task for sleep agent")
        print("SUCCESS: Task added to queue")
        
        # Check status
        status = agent.get_status()
        print(f"Agent Status - State: {status['state']}, Queue: {status['queue_size']}")
        
        # Let it process briefly
        time.sleep(3)
        
        # Check final status
        final_status = agent.get_status()
        print(f"Final Status - State: {final_status['state']}, Queue: {final_status['queue_size']}")
        
        agent.stop()
        print("SUCCESS: Sync agent stopped")
        return True
        
    except Exception as e:
        print(f"ERROR: Sync agent test failed - {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_async_sleep_agent():
    """Test the async sleep-time agent."""
    print("\nTesting Async Sleep Agent...")
    print("=" * 30)
    
    try:
        from sleep_time.async_sleeper_agent import AsyncSleepTimeAgent
        
        agent = AsyncSleepTimeAgent(max_concurrent_tasks=2)
        await agent.start()
        print("SUCCESS: Async agent started")
        
        # Add a simple task
        await agent.add_task("Test async task for sleep agent")
        print("SUCCESS: Async task added to queue")
        
        # Check status
        status = await agent.get_status()
        print(f"Async Status - State: {status['state']}, Queue: {status['queue_size']}")
        
        # Let it process briefly
        await asyncio.sleep(3)
        
        # Check final status
        final_status = await agent.get_status()
        print(f"Final Async Status - State: {final_status['state']}, Queue: {final_status['queue_size']}")
        
        await agent.stop()
        print("SUCCESS: Async agent stopped")
        return True
        
    except Exception as e:
        print(f"ERROR: Async agent test failed - {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run sleep agent tests."""
    print("Sleep-Time Agent Test Suite")
    print("=" * 40)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test memory first
    memory_ok = test_memory_system()
    
    # Test sync agent
    sync_ok = test_sync_sleep_agent() if memory_ok else False
    
    # Test async agent
    async_ok = await test_async_sleep_agent() if memory_ok else False
    
    print(f"\nTest Results:")
    print(f"Memory System: {'PASS' if memory_ok else 'FAIL'}")
    print(f"Sync Agent: {'PASS' if sync_ok else 'FAIL'}")
    print(f"Async Agent: {'PASS' if async_ok else 'FAIL'}")
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest suite failed: {e}")
        import traceback
        traceback.print_exc()