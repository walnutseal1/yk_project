#!/usr/bin/env python3
"""
Simple Sleep Agent Test - No Unicode Issues
"""

import requests
import json
import time

def test_sleep_agent():
    """Test the sleep agent via API calls."""
    print("Sleep Agent Test Suite")
    print("=" * 30)
    
    base_url = "http://localhost:5000"
    
    try:
        # Check if server is running
        print("Checking server health...")
        health = requests.get(f"{base_url}/health", timeout=5)
        
        if health.status_code == 200:
            print("SUCCESS: Server is running")
        else:
            print("ERROR: Server not responding")
            return
            
        # Send test message to trigger sleep agent
        print("\nSending message to trigger sleep agent...")
        
        test_message = {
            "message": "Please remember that I am testing memory processing and the sleep agent functionality.",
            "stream": False
        }
        
        response = requests.post(f"{base_url}/chat", json=test_message, timeout=30)
        
        if response.status_code == 200:
            print("SUCCESS: Message processed")
            data = response.json()
            print(f"Response: {data.get('response', '')[:100]}...")
        else:
            print(f"ERROR: Message failed with status {response.status_code}")
            return
            
        # Check current memory state
        print("\nChecking current memory state...")
        memory_resp = requests.get(f"{base_url}/memory/core", timeout=10)
        
        if memory_resp.status_code == 200:
            memory_data = memory_resp.json()
            print("SUCCESS: Memory retrieved")
            
            blocks = memory_data.get('blocks', [])
            print(f"Memory blocks found: {len(blocks)}")
            
            for block in blocks:
                label = block.get('label', 'Unknown')
                updated = block.get('metadata', {}).get('last_updated', 'Never')
                content_len = len(block.get('content', ''))
                print(f"  Block '{label}': {content_len} chars, updated {updated}")
                
        else:
            print("ERROR: Could not retrieve memory")
            
        # Wait for sleep agent processing
        print(f"\nWaiting 10 seconds for sleep agent to process...")
        time.sleep(10)
        
        # Check memory again
        print("Checking memory after sleep agent processing...")
        memory_resp2 = requests.get(f"{base_url}/memory/core", timeout=10)
        
        if memory_resp2.status_code == 200:
            memory_data2 = memory_resp2.json()
            
            for block in memory_data2.get('blocks', []):
                label = block.get('label', 'Unknown')  
                updated = block.get('metadata', {}).get('last_updated', 'Never')
                print(f"  Block '{label}' last updated: {updated}")
                
        print("\nTEST COMPLETE!")
        print("Check server console for 'Processing task created at...' messages")
        
    except requests.ConnectionError:
        print("ERROR: Cannot connect to server. Is it running on localhost:5000?")
    except Exception as e:
        print(f"ERROR: Test failed - {e}")

if __name__ == "__main__":
    test_sleep_agent()