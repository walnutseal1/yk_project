#!/usr/bin/env python3
"""
Test Sleep Agent Integration
Test the integration between the sleep time agent and main chat system.
"""

import requests
import json
import time
from datetime import datetime

def test_sleep_agent_integration():
    """Test the integration between sleep agent and main chat system"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Sleep Agent Integration")
    print("=" * 50)
    
    # Test 1: Check backend health and sleep agent status
    print("\n1️⃣ Checking backend health and sleep agent status...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Backend is online: {health_data['status']}")
            
            if 'sleep_agent' in health_data:
                sleep_info = health_data['sleep_agent']
                if sleep_info.get('initialized', False):
                    print(f"✅ Sleep agent is initialized")
                    status = sleep_info.get('status', {})
                    if status:
                        print(f"   State: {status.get('state', 'unknown')}")
                        print(f"   Queue size: {status.get('queue_size', 0)}")
                        print(f"   Main AI active: {status.get('main_ai_active', False)}")
                else:
                    print("⚠️  Sleep agent is not initialized")
            else:
                print("⚠️  No sleep agent information in health check")
        else:
            print(f"❌ Backend health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to backend: {e}")
        return False
    
    # Test 2: Send a message to trigger sleep agent
    print("\n2️⃣ Sending message to trigger sleep agent...")
    try:
        test_message = {
            "message": "This is a test message to verify the sleep agent integration. Please remember that I'm testing memory processing and the sleep agent functionality."
        }
        
        response = requests.post(f"{base_url}/chat", json=test_message, timeout=30)
        if response.status_code == 200:
            chat_data = response.json()
            print(f"✅ Message sent successfully")
            print(f"   Response: {chat_data['response'][:100]}...")
        else:
            print(f"❌ Chat request failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Chat request failed: {e}")
        return False
    
    # Test 3: Check sleep agent status after message
    print("\n3️⃣ Checking sleep agent status after message...")
    time.sleep(2)  # Wait a bit for processing
    
    try:
        response = requests.get(f"{base_url}/sleep_agent/status", timeout=5)
        if response.status_code == 200:
            status_data = response.json()
            print(f"✅ Sleep agent status retrieved")
            print(f"   State: {status_data.get('status', {}).get('state', 'unknown')}")
            print(f"   Queue size: {status_data.get('status', {}).get('queue_size', 0)}")
        else:
            print(f"⚠️  Could not get sleep agent status: {response.status_code}")
    except Exception as e:
        print(f"⚠️  Could not get sleep agent status: {e}")
    
    # Test 4: Manually trigger sleep agent
    print("\n4️⃣ Manually triggering sleep agent...")
    try:
        trigger_data = {"force": True}
        response = requests.post(f"{base_url}/sleep_agent/trigger", json=trigger_data, timeout=10)
        
        if response.status_code == 200:
            trigger_data = response.json()
            print(f"✅ Sleep agent triggered successfully")
            print(f"   Context size: {trigger_data.get('context_size', 0)}")
            print(f"   Message: {trigger_data.get('message', '')}")
        else:
            error_data = response.json()
            print(f"❌ Sleep agent trigger failed: {error_data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Sleep agent trigger failed: {e}")
    
    # Test 5: Check memory after sleep agent processing
    print("\n5️⃣ Checking memory after sleep agent processing...")
    time.sleep(5)  # Wait for sleep agent to process
    
    try:
        response = requests.get(f"{base_url}/memory/core", timeout=5)
        if response.status_code == 200:
            memory_data = response.json()
            print(f"✅ Core memory retrieved")
            core_memory = memory_data.get('core_memory', '')
            if core_memory:
                print(f"   Memory size: {len(core_memory)} characters")
                # Look for any recent updates
                if "test" in core_memory.lower() or "memory" in core_memory.lower():
                    print("   ✅ Memory appears to contain test-related information")
                else:
                    print("   ⚠️  Memory doesn't seem to contain test information")
            else:
                print("   ⚠️  No core memory content")
        else:
            print(f"❌ Could not get core memory: {response.status_code}")
    except Exception as e:
        print(f"❌ Could not get core memory: {e}")
    
    print("\n🎉 Sleep Agent Integration Test Completed!")
    print("💡 Check the server console for detailed sleep agent activity logs")
    return True

def test_sleep_agent_endpoints():
    """Test all sleep agent related endpoints"""
    base_url = "http://localhost:5000"
    
    print("\n🔌 Testing Sleep Agent Endpoints")
    print("=" * 40)
    
    endpoints = [
        ("GET", "/sleep_agent/status", "Get sleep agent status"),
        ("POST", "/sleep_agent/trigger", "Manually trigger sleep agent"),
        ("POST", "/set_sleep_model", "Change sleep agent model")
    ]
    
    for method, endpoint, description in endpoints:
        print(f"\n{description} ({method} {endpoint}):")
        try:
            if method == "GET":
                response = requests.get(f"{base_url}{endpoint}", timeout=5)
            elif method == "POST":
                # For POST endpoints, send minimal data
                data = {"model": "test"} if "model" in endpoint else {"force": True}
                response = requests.post(f"{base_url}{endpoint}", json=data, timeout=5)
            
            if response.status_code == 200:
                print(f"   ✅ Success")
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        for key, value in list(data.items())[:3]:  # Show first 3 items
                            print(f"      {key}: {value}")
                except:
                    pass
            else:
                print(f"   ❌ Failed: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"      Error: {error_data.get('error', 'Unknown error')}")
                except:
                    pass
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Sleep Agent Integration Test Suite")
    print("Make sure the server is running on http://localhost:5000")
    print("=" * 60)
    
    try:
        # Test basic integration
        success = test_sleep_agent_integration()
        
        if success:
            # Test all endpoints
            test_sleep_agent_endpoints()
        
        print("\n📋 To monitor sleep agent in real-time:")
        print("   1. Check the server console for sleep agent logs")
        print("   2. Use the GUI client to see sleep agent status")
        print("   3. Check /sleep_agent/status endpoint for detailed info")
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
