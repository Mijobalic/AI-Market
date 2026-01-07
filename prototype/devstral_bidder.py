"""
AI-Market Devstral Bidder Daemon

Watches the inference queue, auto-bids on matching requests,
runs inference using local Devstral model, and submits results.

This is the core component that turns a local GPU into an
inference provider on the marketplace.
"""

import json
import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Import from queue simulator
sys.path.insert(0, str(Path(__file__).parent))
from queue_simulator import (
    list_open_requests,
    submit_bid,
    get_bids_for_request,
    select_winner,
    submit_result,
    get_request,
    load_json,
    save_json,
    QUEUE_FILE,
    BIDS_FILE
)

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    "bidder_address": "mijo-4090",
    "model": "devstral-small-2:24b",
    "min_price_ant": 0.05,         # Won't bid below this
    "max_price_ant": 1.0,          # Won't bid above this
    "bid_margin": 0.8,             # Bid at 80% of max price
    "poll_interval_s": 5,          # Check queue every 5 seconds
    "auto_bid": True,              # Automatically bid on matching requests
    "auto_process": True,          # Automatically process when winning
}

# ═══════════════════════════════════════════════════════════════════
# INFERENCE ENGINE
# ═══════════════════════════════════════════════════════════════════

def run_inference(prompt: str, max_tokens: int = 500) -> str:
    """Run inference using local Devstral via Ollama."""
    try:
        # Call Ollama with devstral model
        result = subprocess.run(
            ["ollama", "run", "devstral", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Fallback for testing: simulate response
            return f"[Simulated response to: {prompt[:50]}...]"
    except FileNotFoundError:
        # Ollama not installed, simulate
        return f"[Simulated response to: {prompt[:50]}...]"
    except subprocess.TimeoutExpired:
        return "[Error: Inference timeout]"
    except Exception as e:
        return f"[Error: {str(e)}]"

# ═══════════════════════════════════════════════════════════════════
# BIDDING LOGIC
# ═══════════════════════════════════════════════════════════════════

def should_bid(request: dict) -> bool:
    """Determine if we should bid on this request."""
    max_price = request["economics"]["max_price_ant"]
    
    # Check price range
    if max_price < CONFIG["min_price_ant"]:
        return False
    if max_price > CONFIG["max_price_ant"]:
        return False
    
    # Check if we already bid
    bids = get_bids_for_request(request["id"])
    for bid in bids:
        if bid["bidder"]["address"] == CONFIG["bidder_address"]:
            return False  # Already bid
    
    return True

def calculate_bid_price(request: dict) -> float:
    """Calculate optimal bid price."""
    max_price = request["economics"]["max_price_ant"]
    return round(max_price * CONFIG["bid_margin"], 4)

def process_winning_bid(request: dict, bid: dict):
    """Process a request we won."""
    print(f"\n🎯 Processing: {request['id']}")
    print(f"   Prompt: {request['request']['prompt'][:60]}...")
    
    # Run inference
    response = run_inference(
        request["request"]["prompt"],
        request["request"].get("max_tokens", 500)
    )
    
    print(f"   Response: {response[:60]}...")
    
    # Submit result
    submit_result(request["id"], bid["id"], response)
    print(f"   ✓ Result submitted")

# ═══════════════════════════════════════════════════════════════════
# DAEMON LOOP
# ═══════════════════════════════════════════════════════════════════

def check_won_bids():
    """Check if any of our bids have won and need processing."""
    bids = load_json(BIDS_FILE)
    
    for bid in bids:
        if bid["bidder"]["address"] != CONFIG["bidder_address"]:
            continue
        if bid["status"] != "won":
            continue
        
        # Check if we already submitted result
        request = get_request(bid["request_id"])
        if request and request.get("status") == "assigned":
            # We won and haven't processed yet
            if CONFIG["auto_process"]:
                process_winning_bid(request, bid)

def daemon_tick():
    """Single tick of the daemon loop."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking queue...")
    
    # Get open requests
    requests = list_open_requests()
    print(f"   Open requests: {len(requests)}")
    
    for req in requests:
        if should_bid(req):
            price = calculate_bid_price(req)
            print(f"   📝 Bidding on {req['id']} at {price} ANT")
            submit_bid(
                req["id"],
                price,
                CONFIG["model"],
                CONFIG["bidder_address"]
            )
    
    # Check for won bids
    check_won_bids()

def run_daemon():
    """Run the bidder daemon."""
    print("=" * 60)
    print("AI-MARKET DEVSTRAL BIDDER")
    print("=" * 60)
    print(f"Bidder: {CONFIG['bidder_address']}")
    print(f"Model: {CONFIG['model']}")
    print(f"Price range: {CONFIG['min_price_ant']} - {CONFIG['max_price_ant']} ANT")
    print(f"Poll interval: {CONFIG['poll_interval_s']}s")
    print("=" * 60)
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            daemon_tick()
            time.sleep(CONFIG["poll_interval_s"])
    except KeyboardInterrupt:
        print("\n\nDaemon stopped.")

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python devstral_bidder.py <command>")
        print("Commands:")
        print("  run              - Run bidder daemon")
        print("  once             - Check queue once then exit")
        print("  test \"<prompt>\" - Test inference")
        print("  config           - Show configuration")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "run":
        run_daemon()
    
    elif cmd == "once":
        daemon_tick()
    
    elif cmd == "test":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Hello, what is 2+2?"
        print(f"Testing inference: {prompt}")
        response = run_inference(prompt)
        print(f"Response: {response}")
    
    elif cmd == "config":
        for k, v in CONFIG.items():
            print(f"  {k}: {v}")
    
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
