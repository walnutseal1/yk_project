#!/usr/bin/env python3
"""
Test Memory Direct - No Path Issues
"""

import requests
import json

def test_memory_endpoint():
    """Test the memory endpoint directly."""
    print("Testing Memory Endpoint")
    print("=" * 25)
    
    try:
        response = requests.get("http://localhost:5000/memory/core", timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print("SUCCESS: Got JSON response")
            print(f"Keys in response: {list(data.keys())}")
            
            if 'core_memory' in data:
                memory = data['core_memory']
                print(f"Core memory length: {len(memory)} chars")
                print(f"Memory preview: {memory[:100]}...")
            else:
                print("No core_memory in response")
                
        else:
            print(f"ERROR: {response.text}")
            
    except requests.ConnectionError:
        print("ERROR: Cannot connect to server")
    except Exception as e:
        print(f"ERROR: {e}")

def test_health_endpoint():
    """Test health endpoint for comparison."""
    print("\nTesting Health Endpoint (for comparison)")
    print("=" * 40)
    
    try:
        response = requests.get("http://localhost:5000/health", timeout=5)
        print(f"Health Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Health Response: {data}")
            
            ai_initialized = data.get('ai_system_initialized', False)
            print(f"AI System Initialized: {ai_initialized}")
            
            if not ai_initialized:
                print("WARNING: AI system not initialized - this could cause memory endpoint to fail")
            else:
                print("AI system is ready")
                
    except Exception as e:
        print(f"Health check failed: {e}")

if __name__ == "__main__":
    test_health_endpoint()
    test_memory_endpoint()
    
    print("\nNext Steps:")
    print("- If AI system not initialized, that's the root cause")
    print("- Check server console for initialization errors")
    print("- Memory endpoint needs AI system to be ready first")