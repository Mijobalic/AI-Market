"""
Autonomi-Aware Smart Bidder

Watches the Autonomi request feed and bids on suitable requests.
Uses real Devstral inference via Mistral API.
"""

import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# Import existing components
from request_feed import RequestFeed
from smart_bidder import (
    analyze_prompt,
    calculate_smart_price,
    calculate_capability_match,
    run_inference,
    estimate_quality,
    record_job,
    load_reputation,
    CONFIG
)
from autonomi_client import AutonomiClient

class AutonomiBidder:
    """Smart bidder that operates on the Autonomi network."""
    
    def __init__(self):
        self.feed = RequestFeed(backend="anttp")
        self.client = AutonomiClient(backend="anttp")
        self.bidder_id = "mellanrum-free-ai"
    
    def check_feed(self) -> List[Dict]:
        """Get open requests from the feed."""
        return self.feed.get_open_requests()
    
    def should_bid(self, request: dict) -> bool:
        """Decide whether to bid on a request."""
        # Get full request details from Autonomi
        full_request = self.feed.get_request(request["address"])
        if not full_request:
            return False
        
        # Analyze the prompt
        analysis = analyze_prompt(full_request.get("prompt", ""))
        
        # Check capability match
        match = calculate_capability_match(CONFIG["primary_model"], analysis["category"])
        
        # Don't bid if poor match
        if match < 0.5:
            print(f"  Skipping: capability match too low ({match:.2f})")
            return False
        
        return True
    
    def create_bid(self, request: dict) -> dict:
        """Create a bid for a request."""
        full_request = self.feed.get_request(request["address"])
        analysis = analyze_prompt(full_request.get("prompt", ""))
        
        # Get max price from request and calculate our bid
        max_price = full_request.get("max_price_ant", 0.1)
        capability = calculate_capability_match(CONFIG["primary_model"], analysis["category"])
        
        # Price based on complexity and capability
        base_price = max_price * 0.3 * (1 + analysis["complexity"] / 10)
        # Discount for high capability match
        bid_price = base_price * (0.5 + 0.5 * capability)
        # Ensure we don't bid above max
        bid_price = min(bid_price, max_price * 0.9)
        
        bid = {
            "type": "ai_market_bid",
            "version": "0.1",
            "request_address": request["address"],
            "request_id": request["request_id"],
            "bidder": self.bidder_id,
            "price_ant": round(bid_price, 4),
            "model": CONFIG["primary_model"],
            "capability_match": capability,
            "estimated_time_seconds": 30,
            "created": datetime.now().isoformat()
        }
        
        return bid
    
    def submit_bid(self, bid: dict) -> Optional[str]:
        """Submit bid to Autonomi."""
        address = self.client.backend.upload_data(bid)
        if address:
            print(f"✓ Bid submitted: {bid['price_ant']:.4f} ANT")
            print(f"  Address: {address}")
        return address
    
    def execute_job(self, request_address: str, bid_address: str) -> dict:
        """Execute the inference job and return result."""
        request = self.feed.get_request(request_address)
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", 500)
        
        print(f"🤖 Executing inference...")
        print(f"   Prompt: {prompt[:50]}...")
        
        # Run real inference
        response = run_inference(prompt, CONFIG["primary_model"], max_tokens)
        analysis = analyze_prompt(prompt)
        quality = estimate_quality(response, prompt, analysis)
        
        result = {
            "type": "ai_market_result",
            "version": "0.1",
            "request_address": request_address,
            "bid_address": bid_address,
            "bidder": self.bidder_id,
            "response": response,
            "quality_estimate": quality,
            "model_used": CONFIG["primary_model"],
            "completed": datetime.now().isoformat()
        }
        
        return result
    
    def submit_result(self, result: dict) -> Optional[str]:
        """Submit result to Autonomi."""
        address = self.client.backend.upload_data(result)
        if address:
            print(f"✓ Result submitted")
            print(f"  Address: {address}")
            print(f"  Quality: {result['quality_estimate']:.2f}")
        return address
    
    def run_once(self):
        """Check feed once and process any open requests."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking Autonomi feed...")
        
        requests = self.check_feed()
        print(f"   Open requests: {len(requests)}")
        
        for req in requests:
            print(f"\n📝 {req['request_id']}")
            
            if self.should_bid(req):
                # Create and submit bid
                bid = self.create_bid(req)
                bid_address = self.submit_bid(bid)
                
                if bid_address:
                    # For demo: immediately execute (normally would wait for selection)
                    result = self.execute_job(req["address"], bid_address)
                    result_address = self.submit_result(result)
                    
                    if result_address:
                        # Update reputation
                        analysis = analyze_prompt(
                            self.feed.get_request(req["address"]).get("prompt", "")
                        )
                        record_job(
                            analysis["category"],
                            bid["price_ant"],
                            result["quality_estimate"]
                        )
                        
                        # Mark request as complete in local feed
                        self.feed.mark_complete(req["request_id"], result_address)
                        
                        print(f"✓ Job complete! Response preview:")
                        print(f"   {result['response'][:100]}...")


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python autonomi_bidder.py <command>")
        print("Commands:")
        print("  once    - Check feed once and process")
        print("  watch   - Continuously watch feed")
        print("  status  - Show reputation status")
        return
    
    cmd = sys.argv[1]
    bidder = AutonomiBidder()
    
    if cmd == "once":
        bidder.run_once()
    
    elif cmd == "watch":
        print("🔄 Watching Autonomi feed for requests...")
        print("   Press Ctrl+C to stop\n")
        while True:
            try:
                bidder.run_once()
                time.sleep(30)
            except KeyboardInterrupt:
                print("\n👋 Stopping bidder")
                break
    
    elif cmd == "status":
        rep = load_reputation()
        print("Autonomi Bidder Status:")
        print(f"  ID: {bidder.bidder_id}")
        print(f"  Total jobs: {rep['total_jobs']}")
        print(f"  Total earned: {rep['total_earned']:.4f} ANT")
        print(f"  Average quality: {rep['average_quality']:.2f}")


if __name__ == "__main__":
    main()
