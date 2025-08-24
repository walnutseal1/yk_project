#!/usr/bin/env python3
"""
Quick Sleep Agent Test
Test the sleep agent that's currently running in your system.
"""

import requests
import json
import time

def test_sleep_agent_via_api():
    """Test sleep agent by sending messages through the API."""
    print("🧪 Testing Sleep Agent via API...")
    print("=" * 40)
    
    base_url = "http://localhost:5000"
    
    try:
        # Test 1: Health check
        print("🔍 Checking if server is running...")
        health = requests.get(f"{base_url}/health", timeout=5)
        if health.status_code == 200:
            print("✅ Server is running")
        else:
            print("❌ Server not responding")
            return
            
        # Test 2: Send a message that should trigger sleep agent
        print("\n📤 Sending test message...")
        test_message = {
            "message": "Please remember that I'm testing the sleep agent functionality and memory processing.",
            "stream": False
        }
        
        response = requests.post(f"{base_url}/chat", json=test_message, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Message sent successfully")
            print(f"📨 Response: {data.get('response', 'No response')[:100]}...")
        else:
            print(f"❌ Message failed: {response.status_code}")
            
        # Test 3: Send multiple messages to trigger sleep agent processing
        print("\n📤 Sending multiple messages to trigger background processing...")
        
        messages = [
            "I love working with AI optimization and performance tuning.",
            "The async Ollama improvements are really impressive!",
            "Memory management is crucial for AI systems."
        ]
        
        for i, msg in enumerate(messages, 1):
            print(f"   Sending message {i}/3...")
            test_msg = {"message": msg, "stream": False}
            
            try:
                resp = requests.post(f"{base_url}/chat", json=test_msg, timeout=20)
                if resp.status_code == 200:
                    print(f"   ✅ Message {i} processed")
                else:
                    print(f"   ❌ Message {i} failed")
            except requests.RequestException as e:
                print(f"   ❌ Message {i} error: {e}")
            
            # Small delay between messages
            time.sleep(2)
            
        # Test 4: Check memory after processing
        print("\n🧠 Checking memory after processing...")
        try:
            memory_resp = requests.get(f"{base_url}/memory/core", timeout=10)
            if memory_resp.status_code == 200:
                memory_data = memory_resp.json()
                print("✅ Memory retrieved successfully")
                
                # The API returns core_memory as a string, not blocks
                core_memory_str = memory_data.get('core_memory', '')
                print(f"📊 Core memory length: {len(core_memory_str)} characters")
                
                # Extract memory block info from the string
                if '<memory_blocks>' in core_memory_str:
                    blocks_section = core_memory_str.split('<memory_blocks>')[1].split('</memory_blocks>')[0]
                    print("📝 Memory blocks found in core memory")
                else:
                    print("📝 No memory blocks section found")
                    
            else:
                print("❌ Could not retrieve memory")
        except requests.RequestException as e:
            print(f"❌ Memory check failed: {e}")
            
        print("\n⏳ Waiting 15 seconds for sleep agent to process...")
        print("   (The sleep agent runs in the background after conversations)")
        
        # Wait for sleep agent to potentially process
        for i in range(15):
            print(f"   Waiting... {15-i}s remaining", end='\r')
            time.sleep(1)
        print("\n")
        
        # Test 5: Check memory again for any changes
        print("🧠 Checking memory for sleep agent updates...")
        try:
            memory_resp2 = requests.get(f"{base_url}/memory/core", timeout=10)
            if memory_resp2.status_code == 200:
                memory_data2 = memory_resp2.json()
                print("✅ Memory check complete")
                
                # Check if memory changed
                core_memory_str2 = memory_data2.get('core_memory', '')
                
                # Look for last updated timestamps in the memory string
                import re
                timestamps = re.findall(r'last_updated["\s:]*([0-9T:\-+Z\.]+)', core_memory_str2)
                
                if timestamps:
                    print("📅 Memory block timestamps found:")
                    for i, timestamp in enumerate(timestamps):
                        print(f"   Block {i+1}: {timestamp}")
                else:
                    print("📅 No timestamps found in memory")
                    
            else:
                print("❌ Could not retrieve updated memory")
        except requests.RequestException as e:
            print(f"❌ Memory update check failed: {e}")
            
        print("\n🎉 Sleep agent test completed!")
        print("💡 Check the server console for sleep agent activity logs")
        
    except requests.ConnectionError:
        print("❌ Could not connect to server. Make sure the server is running on localhost:5000")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_manual_memory_trigger():
    """Manual test by checking current memory state."""
    print("\n🔍 Manual Memory State Check...")
    print("=" * 40)
    
    try:
        # Check current memory
        memory_resp = requests.get("http://localhost:5000/memory/core", timeout=5)
        if memory_resp.status_code == 200:
            data = memory_resp.json()
            print("📊 Current Memory State:")
            
            # The API returns core_memory as a formatted string
            core_memory_str = data.get('core_memory', '')
            print(f"📏 Total memory size: {len(core_memory_str)} characters")
            
            # Extract basic info from the memory string
            if 'memory_metadata' in core_memory_str:
                # Look for current time
                import re
                time_match = re.search(r'current time is: ([^\n]+)', core_memory_str)
                if time_match:
                    print(f"🕐 Current time: {time_match.group(1)}")
                    
                # Look for memory block count
                blocks_match = re.search(r'(\d+) total memories.*stored in vector memory', core_memory_str)
                if blocks_match:
                    print(f"🧠 Vector memories: {blocks_match.group(1)}")
                    
            # Show a sample of the memory content
            if len(core_memory_str) > 200:
                print(f"📄 Memory preview: {core_memory_str[:200]}...")
            else:
                print(f"📄 Full memory: {core_memory_str}")
                
        else:
            print("❌ Could not retrieve memory state")
            
    except Exception as e:
        print(f"❌ Memory check failed: {e}")

if __name__ == "__main__":
    print("🧪 Quick Sleep Agent Test Suite")
    print("🚀 Testing sleep agent computation and memory processing...")
    
    # Test current memory state
    test_manual_memory_trigger()
    
    # Test via API
    test_sleep_agent_via_api()
    
    print("\n📋 To monitor sleep agent in real-time:")
    print("   - Watch the server console for 'Processing task created at...' messages")
    print("   - Look for memory update timestamps in the API responses")
    print("   - Check if new information appears in memory blocks")
    print("\n✅ Test complete!")