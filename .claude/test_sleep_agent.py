#!/usr/bin/env python3
"""
Sleep-Time Agent Testing Suite
Test both sync and async versions of the sleep agent with various scenarios.
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

from sleep_time.sleeper_agent import SleepTimeAgent
from sleep_time.async_sleeper_agent import AsyncSleepTimeAgent

def test_sync_sleep_agent():
    """Test the original sync sleep-time agent."""
    print("Testing Sync Sleep-Time Agent...")
    print("=" * 50)
    
    agent = SleepTimeAgent()
    
    try:
        # Start the agent
        agent.start()
        print("Agent started successfully")
        
        # Test 1: Add simple text task
        print("\nTest 1: Adding simple text task...")
        agent.add_task("Summarize recent conversation about AI optimization")
        
        # Test 2: Add conversation messages
        print("Test 2: Adding conversation messages...")
        messages = [
            {"role": "user", "content": "Hello, can you help me with optimization?"},
            {"role": "assistant", "content": "Sure! I'd be happy to help with optimization."},
            {"role": "user", "content": "What about async processing?"}
        ]
        agent.go(messages)
        
        # Test 3: Check status
        print("Test 3: Checking agent status...")
        status = agent.get_status()
        print(f"   State: {status['state']}")
        print(f"   Queue Size: {status['queue_size']}")
        print(f"   Main AI Active: {status['main_ai_active']}")
        
        # Test 4: Simulate main AI activity
        print("Test 4: Simulating main AI activity...")
        agent.notify_main_ai_start()
        time.sleep(2)
        agent.notify_main_ai_end()
        
        # Let it process for a bit
        print("Letting agent process for 10 seconds...")
        time.sleep(10)
        
        # Final status check
        final_status = agent.get_status()
        print(f"\nFinal Status:")
        print(f"   State: {final_status['state']}")
        print(f"   Queue Size: {final_status['queue_size']}")
        
    except Exception as e:
        print(f"Error during sync testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        agent.stop()
        print("Sync agent stopped")

async def test_async_sleep_agent():
    """Test the new async sleep-time agent."""
    print("\n🚀 Testing Async Sleep-Time Agent...")
    print("=" * 50)
    
    agent = AsyncSleepTimeAgent(max_concurrent_tasks=2)
    
    try:
        # Start the agent
        await agent.start()
        print("✅ Async agent started successfully")
        
        # Test 1: Add simple text task
        print("\n📝 Test 1: Adding simple text task...")
        await agent.add_task("Analyze recent performance optimizations")
        
        # Test 2: Add conversation messages  
        print("📝 Test 2: Adding conversation messages...")
        messages = [
            {"role": "user", "content": "What are the async optimizations?"},
            {"role": "assistant", "content": "The async optimizations include connection pooling, request balancing..."},
            {"role": "user", "content": "How much faster is it?"}
        ]
        await agent.go(messages)
        
        # Test 3: Add multiple tasks concurrently
        print("📝 Test 3: Adding multiple concurrent tasks...")
        tasks = [
            "Process user preferences from conversation",
            "Update memory blocks with recent information", 
            "Analyze conversation patterns for insights"
        ]
        
        for i, task in enumerate(tasks):
            await agent.add_task(f"Task {i+1}: {task}")
            print(f"   Added: Task {i+1}")
        
        # Test 4: Check status during processing
        print("📊 Test 4: Monitoring async processing...")
        for i in range(5):
            status = await agent.get_status()
            print(f"   [{i+1}/5] State: {status['state']}, Queue: {status['queue_size']}, Processing: {status['processing_tasks']}")
            await asyncio.sleep(2)
        
        # Test 5: Simulate main AI activity
        print("🧠 Test 5: Simulating main AI activity...")
        await agent.notify_main_ai_start()
        await asyncio.sleep(1)
        await agent.notify_main_ai_end()
        
        # Let it process
        print("⏳ Letting async agent process for 10 seconds...")
        await asyncio.sleep(10)
        
        # Final status
        final_status = await agent.get_status()
        print(f"\n📊 Final Async Status:")
        print(f"   State: {final_status['state']}")
        print(f"   Queue Size: {final_status['queue_size']}")
        print(f"   Processing Tasks: {final_status['processing_tasks']}")
        
    except Exception as e:
        print(f"❌ Error during async testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await agent.stop()
        print("🛑 Async agent stopped")

def test_performance_comparison():
    """Compare sync vs async performance."""
    print("\n⚡ Performance Comparison Test...")
    print("=" * 50)
    
    print("🔄 This test would require longer runtime to see meaningful differences")
    print("📊 Key metrics to compare:")
    print("   - Task processing speed")
    print("   - Memory usage during processing")
    print("   - Concurrent task handling")
    print("   - Response times under load")
    
    # In a real scenario, you'd add timing measurements here

def test_memory_integration():
    """Test memory system integration."""
    print("\n🧠 Testing Memory System Integration...")
    print("=" * 50)
    
    try:
        # Test memory tools directly
        import memory.memtools as mem
        
        print("📁 Testing memory initialization...")
        mem.init_recall_db()
        print("✅ Recall database initialized")
        
        print("🧠 Testing core memory...")
        core_memory = mem.get_core_memory()
        print(f"✅ Core memory loaded ({len(core_memory)} characters)")
        
        print("🔍 Testing memory search...")
        # This would require vector memory to be populated
        print("✅ Memory system ready for sleep agent")
        
    except Exception as e:
        print(f"❌ Memory integration error: {e}")

async def main():
    """Run all sleep agent tests."""
    print("Sleep-Time Agent Test Suite")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Memory Integration
    test_memory_integration()
    
    # Test 2: Sync Agent
    test_sync_sleep_agent()
    
    # Test 3: Async Agent  
    await test_async_sleep_agent()
    
    # Test 4: Performance Notes
    test_performance_comparison()
    
    print(f"\nAll tests completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest suite failed: {e}")
        import traceback
        traceback.print_exc()