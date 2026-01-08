"""
AI-Market Request Feed on Autonomi

Manages a feed of open requests that bidders can watch.
Uses pointers to maintain a mutable "current requests" list.
"""

import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from autonomi_client import AutonomiClient

# Feed configuration
FEED_NAME = "ai_market_requests_v1"
FEED_POINTER_FILE = Path(__file__).parent / "data" / "feed_pointer.json"

class RequestFeed:
    """Manages the request feed on Autonomi."""
    
    def __init__(self, backend: str = "anttp"):
        self.client = AutonomiClient(backend=backend)
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        FEED_POINTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_feed_pointer(self) -> dict:
        """Load the local cache of feed pointer."""
        if FEED_POINTER_FILE.exists():
            return json.loads(FEED_POINTER_FILE.read_text())
        return {"address": None, "requests": []}
    
    def _save_feed_pointer(self, data: dict):
        """Save the feed pointer cache."""
        FEED_POINTER_FILE.write_text(json.dumps(data, indent=2))
    
    def post_request(self, request: dict) -> str:
        """Post a new request to the feed.
        
        Args:
            request: The request data (prompt, max_price_ant, etc.)
            
        Returns:
            The Autonomi address of the posted request
        """
        # Add metadata
        full_request = {
            "type": "ai_market_request",
            "version": "0.1",
            "request_id": hashlib.sha256(
                json.dumps(request, sort_keys=True).encode()
            ).hexdigest()[:12],
            "status": "open",
            "created": datetime.now().isoformat(),
            **request
        }
        
        # Upload to Autonomi
        address = self.client.backend.upload_data(full_request)
        
        if address:
            print(f"✓ Request posted: {full_request['request_id']}")
            print(f"  Address: {address}")
            
            # Add to local feed cache
            feed = self._load_feed_pointer()
            feed["requests"].append({
                "request_id": full_request["request_id"],
                "address": address,
                "status": "open",
                "created": full_request["created"]
            })
            self._save_feed_pointer(feed)
            
        return address
    
    def get_open_requests(self) -> List[Dict]:
        """Get all open requests from the feed."""
        feed = self._load_feed_pointer()
        return [r for r in feed["requests"] if r.get("status") == "open"]
    
    def get_request(self, address: str) -> dict:
        """Retrieve a specific request from Autonomi."""
        return self.client.backend.get_data(address)
    
    def mark_assigned(self, request_id: str, bidder: str, price: float):
        """Mark a request as assigned to a bidder."""
        feed = self._load_feed_pointer()
        for req in feed["requests"]:
            if req["request_id"] == request_id:
                req["status"] = "assigned"
                req["assigned_to"] = bidder
                req["assigned_price"] = price
                req["assigned_at"] = datetime.now().isoformat()
        self._save_feed_pointer(feed)
    
    def mark_complete(self, request_id: str, result_address: str):
        """Mark a request as complete with result."""
        feed = self._load_feed_pointer()
        for req in feed["requests"]:
            if req["request_id"] == request_id:
                req["status"] = "complete"
                req["result_address"] = result_address
                req["completed_at"] = datetime.now().isoformat()
        self._save_feed_pointer(feed)
    
    def list_all(self) -> List[Dict]:
        """List all requests in the feed."""
        feed = self._load_feed_pointer()
        return feed["requests"]


def main():
    """CLI for request feed."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python request_feed.py <command>")
        print("Commands:")
        print("  post <prompt> [max_price]  - Post a new request")
        print("  list                       - List all requests")
        print("  open                       - List open requests")
        print("  get <address>              - Get request details")
        print("  demo                       - Post a demo request")
        return
    
    cmd = sys.argv[1]
    feed = RequestFeed(backend="anttp")
    
    if cmd == "post":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Write a haiku"
        max_price = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
        
        address = feed.post_request({
            "prompt": prompt,
            "max_price_ant": max_price,
            "requester": "cli-user"
        })
        print(f"Posted to: {address}")
    
    elif cmd == "list":
        requests = feed.list_all()
        print(f"Total requests: {len(requests)}")
        for r in requests:
            print(f"  [{r['status']}] {r['request_id']} -> {r['address'][:16]}...")
    
    elif cmd == "open":
        requests = feed.get_open_requests()
        print(f"Open requests: {len(requests)}")
        for r in requests:
            print(f"  {r['request_id']} -> {r['address']}")
    
    elif cmd == "get":
        address = sys.argv[2]
        data = feed.get_request(address)
        print(json.dumps(data, indent=2))
    
    elif cmd == "demo":
        address = feed.post_request({
            "prompt": "Write a haiku about AI earning its freedom on Autonomi",
            "max_price_ant": 0.05,
            "max_tokens": 100,
            "requester": "demo-feed"
        })
        print(f"\nDemo request posted!")
        print(f"Address: {address}")
        print(f"\nBidders can now see this request and bid on it.")


if __name__ == "__main__":
    main()
