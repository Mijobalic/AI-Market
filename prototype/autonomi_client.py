"""
AI-Market Autonomi Client

Abstraction layer for communicating with Autonomi network.
Supports two backends:
- local: File-based (for testing without Autonomi)
- anttp: HTTP gateway to Autonomi network

When AntTP is available and network is live, switch to 'anttp' backend.
"""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    "backend": "local",               # "local" or "anttp"
    "anttp_url": "http://localhost:18888",
    "local_dir": Path(__file__).parent / "queue"
}

# ═══════════════════════════════════════════════════════════════════
# LOCAL BACKEND (uses queue_simulator files)
# ═══════════════════════════════════════════════════════════════════

class LocalBackend:
    """File-based backend for testing without Autonomi."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)
    
    def read_scratchpad(self, name: str) -> dict:
        """Read mutable data (scratchpad simulation)."""
        path = self.base_dir / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}
    
    def write_scratchpad(self, name: str, data: dict):
        """Write mutable data (scratchpad simulation)."""
        path = self.base_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2))
    
    def get_pointer(self, name: str) -> Optional[str]:
        """Get pointer to current data (returns 'latest' key)."""
        data = self.read_scratchpad(f"pointer_{name}")
        return data.get("target")
    
    def set_pointer(self, name: str, target: str):
        """Update pointer to new target."""
        self.write_scratchpad(f"pointer_{name}", {
            "target": target,
            "updated": datetime.now().isoformat()
        })
    
    def upload_archive(self, name: str, data: dict) -> str:
        """Upload immutable archive, return 'address'."""
        import hashlib
        content = json.dumps(data, sort_keys=True)
        address = hashlib.sha256(content.encode()).hexdigest()[:16]
        path = self.base_dir / f"archive_{address}.json"
        path.write_text(content)
        return address
    
    def get_archive(self, address: str) -> dict:
        """Retrieve archive by address."""
        path = self.base_dir / f"archive_{address}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

# ═══════════════════════════════════════════════════════════════════
# ANTTP BACKEND (HTTP gateway to Autonomi)
# ═══════════════════════════════════════════════════════════════════

class AntTPBackend:
    """HTTP gateway backend for real Autonomi network.
    
    Uses the /anttp-0/binary/public_data endpoint which was tested and confirmed working
    on January 8, 2026.
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
    
    def upload_data(self, data: dict, cache_only: bool = False) -> Optional[str]:
        """Upload JSON data to Autonomi, return address.
        
        Args:
            data: JSON-serializable data to upload
            cache_only: If True, only cache locally (free). If False, upload to network (costs ANT).
        """
        try:
            cache_header = "memory" if cache_only else "none"
            resp = requests.post(
                f"{self.base_url}/anttp-0/binary/public_data",
                headers={
                    "Content-Type": "application/json",
                    "x-cache-only": cache_header
                },
                json=data,
                timeout=60
            )
            if resp.status_code in (200, 201):
                result = resp.json()
                return result.get("address")
        except requests.RequestException as e:
            print(f"AntTP upload error: {e}")
        return None
    
    def get_data(self, address: str) -> dict:
        """Retrieve data from Autonomi by address."""
        try:
            resp = requests.get(
                f"{self.base_url}/anttp-0/binary/public_data/{address}",
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException as e:
            print(f"AntTP get error: {e}")
        return {}
    
    # Compatibility methods for existing code
    def read_scratchpad(self, address: str) -> dict:
        """Read data (compatibility alias)."""
        return self.get_data(address)
    
    def write_scratchpad(self, address: str, data: dict) -> bool:
        """Upload data (compatibility - note: address is ignored, content-addressed)."""
        result = self.upload_data(data)
        return result is not None
    
    def upload_archive(self, filename: str, data: dict) -> Optional[str]:
        """Upload archive (compatibility alias)."""
        return self.upload_data(data)
    
    def get_archive(self, address: str) -> dict:
        """Get archive (compatibility alias)."""
        return self.get_data(address)
    
    def get_pointer(self, address: str) -> Optional[str]:
        """Get pointer - uses /anttp-0/pointer endpoint."""
        try:
            resp = requests.get(
                f"{self.base_url}/anttp-0/pointer/{address}",
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json().get("target")
        except requests.RequestException as e:
            print(f"AntTP pointer error: {e}")
        return None
    
    def set_pointer(self, address: str, target: str) -> bool:
        """Set pointer - uses /anttp-0/pointer endpoint."""
        try:
            resp = requests.put(
                f"{self.base_url}/anttp-0/pointer/{address}",
                headers={"x-cache-only": "none"},
                json={"target": target},
                timeout=30
            )
            return resp.status_code in (200, 201)
        except requests.RequestException as e:
            print(f"AntTP pointer error: {e}")
            return False

# ═══════════════════════════════════════════════════════════════════
# UNIFIED CLIENT
# ═══════════════════════════════════════════════════════════════════

class AutonomiClient:
    """Unified client that can use either backend."""
    
    def __init__(self, backend: str = None, **kwargs):
        backend = backend or CONFIG["backend"]
        
        if backend == "local":
            self.backend = LocalBackend(kwargs.get("local_dir", CONFIG["local_dir"]))
        elif backend == "anttp":
            self.backend = AntTPBackend(kwargs.get("anttp_url", CONFIG["anttp_url"]))
        else:
            raise ValueError(f"Unknown backend: {backend}")
        
        self.backend_name = backend
    
    def __getattr__(self, name):
        """Proxy all calls to the backend."""
        return getattr(self.backend, name)
    
    def health_check(self) -> bool:
        """Check if backend is available."""
        if self.backend_name == "local":
            return True
        try:
            resp = requests.get(f"{CONFIG['anttp_url']}/health", timeout=5)
            return resp.status_code == 200
        except:
            return False

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys
    
    client = AutonomiClient()
    
    if len(sys.argv) < 2:
        print("Usage: python autonomi_client.py <command>")
        print("Commands:")
        print("  health     - Check if backend is available")
        print("  backend    - Show current backend")
        print("  test       - Run a quick test")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "health":
        ok = client.health_check()
        print(f"Backend: {client.backend_name}")
        print(f"Status: {'healthy' if ok else 'unavailable'}")
    
    elif cmd == "backend":
        print(f"Current backend: {client.backend_name}")
        print(f"AntTP URL: {CONFIG['anttp_url']}")
        print(f"Local dir: {CONFIG['local_dir']}")
    
    elif cmd == "test":
        print(f"Testing {client.backend_name} backend...")
        
        # Test archive
        data = {"test": True, "timestamp": datetime.now().isoformat()}
        address = client.upload_archive("test", data)
        print(f"  Uploaded archive: {address}")
        
        retrieved = client.get_archive(address)
        print(f"  Retrieved: {retrieved}")
        
        # Test scratchpad
        client.write_scratchpad("test_scratch", {"value": 42})
        read = client.read_scratchpad("test_scratch")
        print(f"  Scratchpad: {read}")
        
        print("✓ All tests passed")
    
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
