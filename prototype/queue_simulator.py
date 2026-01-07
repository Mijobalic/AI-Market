"""
AI-Market Queue Simulator

A local simulation of the inference marketplace queue.
Uses file-based storage to simulate Autonomi's Scratchpad/Pointer.
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

# Paths
MARKET_DIR = Path(__file__).resolve().parent
QUEUE_FILE = MARKET_DIR / "queue" / "requests.json"
BIDS_FILE = MARKET_DIR / "queue" / "bids.json"
RESULTS_FILE = MARKET_DIR / "queue" / "results.json"

def ensure_dirs():
    """Create queue directory if needed."""
    (MARKET_DIR / "queue").mkdir(exist_ok=True)
    for f in [QUEUE_FILE, BIDS_FILE, RESULTS_FILE]:
        if not f.exists():
            f.write_text("[]")

def load_json(path: Path) -> list:
    """Load JSON array from file."""
    if path.exists():
        return json.loads(path.read_text())
    return []

def save_json(path: Path, data: list):
    """Save JSON array to file."""
    path.write_text(json.dumps(data, indent=2))

# ═══════════════════════════════════════════════════════════════════
# REQUEST MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def create_request(
    prompt: str,
    max_price_ant: float = 0.5,
    model_hint: str = "any",
    max_tokens: int = 500,
    expires_minutes: int = 60,
    requester: str = "anonymous"
) -> dict:
    """Create a new inference request."""
    ensure_dirs()
    
    request = {
        "id": f"req_{uuid.uuid4().hex[:12]}",
        "type": "inference_request",
        "status": "open",
        "created": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(minutes=expires_minutes)).isoformat(),
        "request": {
            "prompt": prompt,
            "model_hint": model_hint,
            "max_tokens": max_tokens
        },
        "economics": {
            "max_price_ant": max_price_ant,
            "payment_mode": "auction"
        },
        "requester": {
            "address": requester,
            "reputation": 0.9
        }
    }
    
    # Add to queue
    queue = load_json(QUEUE_FILE)
    queue.append(request)
    save_json(QUEUE_FILE, queue)
    
    print(f"✓ Created request: {request['id']}")
    return request

def list_open_requests() -> List[dict]:
    """List all open requests."""
    ensure_dirs()
    queue = load_json(QUEUE_FILE)
    now = datetime.now()
    
    open_reqs = []
    for req in queue:
        if req.get("status") == "open":
            expires = datetime.fromisoformat(req["expires"])
            if expires > now:
                open_reqs.append(req)
    return open_reqs

def get_request(request_id: str) -> Optional[dict]:
    """Get a specific request by ID."""
    queue = load_json(QUEUE_FILE)
    for req in queue:
        if req["id"] == request_id:
            return req
    return None

# ═══════════════════════════════════════════════════════════════════
# BID MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def submit_bid(
    request_id: str,
    price_ant: float,
    model: str = "devstral-small-2:24b",
    bidder: str = "local-node"
) -> dict:
    """Submit a bid for a request."""
    ensure_dirs()
    
    bid = {
        "id": f"bid_{uuid.uuid4().hex[:8]}",
        "request_id": request_id,
        "bidder": {
            "address": bidder,
            "model": model,
            "reputation": 0.85
        },
        "bid": {
            "price_ant": price_ant,
            "estimated_time_s": 5,
            "submitted": datetime.now().isoformat()
        },
        "status": "pending"
    }
    
    bids = load_json(BIDS_FILE)
    bids.append(bid)
    save_json(BIDS_FILE, bids)
    
    print(f"✓ Submitted bid: {bid['id']} for {request_id} at {price_ant} ANT")
    return bid

def get_bids_for_request(request_id: str) -> List[dict]:
    """Get all bids for a request."""
    bids = load_json(BIDS_FILE)
    return [b for b in bids if b["request_id"] == request_id]

def select_winner(request_id: str) -> Optional[dict]:
    """Select winning bid (lowest price with reputation > 0.7)."""
    bids = get_bids_for_request(request_id)
    eligible = [b for b in bids if b["bidder"]["reputation"] > 0.7 and b["status"] == "pending"]
    
    if not eligible:
        return None
    
    # Sort by price (lowest first)
    eligible.sort(key=lambda b: b["bid"]["price_ant"])
    winner = eligible[0]
    
    # Update bid status
    all_bids = load_json(BIDS_FILE)
    for b in all_bids:
        if b["id"] == winner["id"]:
            b["status"] = "won"
        elif b["request_id"] == request_id:
            b["status"] = "lost"
    save_json(BIDS_FILE, all_bids)
    
    # Update request status
    queue = load_json(QUEUE_FILE)
    for req in queue:
        if req["id"] == request_id:
            req["status"] = "assigned"
            req["assigned_to"] = winner["id"]
    save_json(QUEUE_FILE, queue)
    
    print(f"✓ Winner selected: {winner['id']} at {winner['bid']['price_ant']} ANT")
    return winner

# ═══════════════════════════════════════════════════════════════════
# RESULT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def submit_result(request_id: str, bid_id: str, response: str) -> dict:
    """Submit inference result."""
    ensure_dirs()
    
    result = {
        "id": f"res_{uuid.uuid4().hex[:8]}",
        "request_id": request_id,
        "bid_id": bid_id,
        "response": response,
        "submitted": datetime.now().isoformat(),
        "validated": None,
        "paid": False
    }
    
    results = load_json(RESULTS_FILE)
    results.append(result)
    save_json(RESULTS_FILE, results)
    
    # Update request status
    queue = load_json(QUEUE_FILE)
    for req in queue:
        if req["id"] == request_id:
            req["status"] = "completed"
    save_json(QUEUE_FILE, queue)
    
    print(f"✓ Result submitted for {request_id}")
    return result

def validate_result(result_id: str, approved: bool) -> dict:
    """Validate a result (approve or reject)."""
    results = load_json(RESULTS_FILE)
    for res in results:
        if res["id"] == result_id:
            res["validated"] = approved
            res["paid"] = approved
            save_json(RESULTS_FILE, results)
            status = "approved" if approved else "rejected"
            print(f"✓ Result {result_id} {status}")
            return res
    return {}

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python queue_simulator.py <command>")
        print("Commands:")
        print("  request \"<prompt>\" [max_price] - Create request")
        print("  list                           - List open requests")
        print("  bid <request_id> <price>       - Submit bid")
        print("  bids <request_id>              - List bids for request")
        print("  select <request_id>            - Select winner")
        print("  result <request_id> <bid_id> \"<response>\" - Submit result")
        print("  validate <result_id> <yes|no>  - Validate result")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "request":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Test prompt"
        price = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
        create_request(prompt, price)
    
    elif cmd == "list":
        reqs = list_open_requests()
        for r in reqs:
            print(f"  {r['id']}: {r['request']['prompt'][:50]}... (max {r['economics']['max_price_ant']} ANT)")
    
    elif cmd == "bid":
        request_id = sys.argv[2]
        price = float(sys.argv[3])
        submit_bid(request_id, price)
    
    elif cmd == "bids":
        request_id = sys.argv[2]
        bids = get_bids_for_request(request_id)
        for b in bids:
            print(f"  {b['id']}: {b['bid']['price_ant']} ANT ({b['status']})")
    
    elif cmd == "select":
        request_id = sys.argv[2]
        select_winner(request_id)
    
    elif cmd == "result":
        request_id = sys.argv[2]
        bid_id = sys.argv[3]
        response = sys.argv[4]
        submit_result(request_id, bid_id, response)
    
    elif cmd == "validate":
        result_id = sys.argv[2]
        approved = sys.argv[3].lower() in ["yes", "y", "true", "1"]
        validate_result(result_id, approved)
    
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
