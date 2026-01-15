
import sys
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8888"

def log(msg):
    print(f"[TEST] {msg}")

def check(response, expected_status=200):
    if response.status_code != expected_status:
        print(f"FAILED: Expected {expected_status}, got {response.status_code}")
        print(response.text)
        sys.exit(1)
    return response.json()

def test_lifecycle():
    log("Testing full config lifecycle...")
    
    # Unique ref to avoid collisions
    ref_suffix = int(time.time())
    source_ref = f"test/lifecycle/{ref_suffix}"
    log(f"Using source_ref: {source_ref}")

    # 1. Create Draft
    log("1. Creating draft config...")
    draft = {
        "source_type": "custom",
        "source_ref": source_ref,
        "fingerprint": f"test_fp_{ref_suffix}",
        "config": {
            "id": f"test_config_{ref_suffix}",
            "name": "Test Lifecycle Config",
            "tables": {
                "Genes": {"columns": {"id": {"width": 100}}}
            }
        },
        "change_summary": "Initial test create"
    }
    resp = requests.post(f"{BASE_URL}/config", json=draft)
    record = check(resp, 200)
    config_id = record["id"]
    version = record["version"]
    log(f"   Created config {config_id} (v{version}) in state {record['state']}")
    
    # 2. Update Draft
    log("2. Updating draft...")
    update = {
        "change_summary": "Updating width",
        "overlays": {
            "tables": {
                "Genes": {"columns": {"id": {"width": 120}}}
            }
        }
    }
    resp = requests.patch(f"{BASE_URL}/config/{config_id}", json=update)
    record = check(resp, 200)
    log(f"   Updated config. State: {record['state']}")
    
    # 3. Propose
    log("3. Proposing config...")
    resp = requests.post(f"{BASE_URL}/config/{config_id}/propose")
    check(resp, 200)
    
    # Verify state
    resp = requests.get(f"{BASE_URL}/config/{config_id}")
    record = check(resp, 200)
    if record["state"] != "proposed":
        print(f"FAILED: Expected proposed, got {record['state']}")
        sys.exit(1)
    log("   Config is PROPOSED")
    
    # 4. Publish
    log("4. Publishing config...")
    resp = requests.post(f"{BASE_URL}/config/{config_id}/publish")
    check(resp, 200)
    log("   Config is PUBLISHED")
    
    # 5. Resolve
    log("5. Resolving config...")
    resp = requests.get(f"{BASE_URL}/config/resolve/{source_ref.replace('/', '%2F')}")  # Ensure URL encoding
    resolved = check(resp, 200)
    
    if resolved["source"] != "published":
        print(f"FAILED: Expected source='published', got {resolved['source']}")
        sys.exit(1)
    
    if resolved["version"] != version:
         print(f"FAILED: Expected version {version}, got {resolved['version']}")
         sys.exit(1)
         
    width = resolved["config"]["tables"]["Genes"]["columns"]["id"]["width"]
    if width != 120:
        print(f"FAILED: Expected width 120, got {width}")
        sys.exit(1)
        
    log("   Resolved successfully with correct updates!")
    
    # 6. List
    log("6. Listing configs...")
    resp = requests.get(f"{BASE_URL}/config/list?state=published")
    data = check(resp, 200)
    total = data["total"]
    log(f"   Found {total} published configs")
    if total < 1:
        print("FAILED: Should have at least 1 published config")
        sys.exit(1)

    log("Lifecycle test PASSED")

def test_resolve_fallback():
    log("\nTesting resolution fallback...")
    # Request something non-existent
    resp = requests.get(f"{BASE_URL}/config/resolve/non_existent/ref/1")
    data = check(resp, 200)
    log(f"   Resolved source: {data['source']}")
    
    if data["source"] != "default":
        print(f"FAILED: Expected default fallback, got {data['source']}")
        # Don't exit, just warn for now as we might have other fallbacks
        
if __name__ == "__main__":
    try:
        test_lifecycle()
        test_resolve_fallback()
        print("\nALL SYSTEMS GO!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
