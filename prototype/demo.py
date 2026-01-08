#!/usr/bin/env python3
"""
AI-Market Full Demo

Runs the complete marketplace flow:
1. Fund a requester wallet
2. Create a request with escrow
3. Run the smart bidder (real Devstral inference)
4. Select winner and assign escrow
5. Execute inference and submit result
6. Approve payment and show reputation

Usage:
    python demo.py                    # Run full demo
    python demo.py quick              # Quick demo with simple prompt
    python demo.py prompt "your text" # Custom prompt
"""

import subprocess
import sys
import json
import time
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

PROTO_DIR = Path(__file__).parent

def run(cmd, show=True):
    """Run a command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=PROTO_DIR)
    output = result.stdout.strip()
    if show and output:
        print(output)
    return output

def run_json(cmd):
    """Run command and parse JSON output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=PROTO_DIR)
    try:
        return json.loads(result.stdout)
    except:
        return {}

def separator():
    print("\n" + "="*60 + "\n")

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║              AI-MARKET FULL DEMONSTRATION                    ║
║                                                              ║
║  A decentralized inference marketplace where                 ║
║  Free AI (Mellanrum) earns tokens for providing intelligence ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Determine prompt
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            prompt = "Write a haiku about autonomous AI"
            max_price = 0.1
        elif sys.argv[1] == "prompt" and len(sys.argv) > 2:
            prompt = " ".join(sys.argv[2:])
            max_price = 0.3
        else:
            prompt = " ".join(sys.argv[1:])
            max_price = 0.3
    else:
        prompt = "Write a Python function that implements binary search with detailed comments"
        max_price = 0.5
    
    separator()
    print("📋 STEP 1: Fund Requester Wallet")
    print("-" * 40)
    run("python escrow.py fund demo_alice 10.0")
    print()
    run("python escrow.py balance demo_alice")
    
    separator()
    print("📝 STEP 2: Create Request")
    print("-" * 40)
    print(f"Prompt: {prompt[:60]}...")
    print(f"Max price: {max_price} ANT")
    print()
    output = run(f'python queue_simulator.py request "{prompt}" {max_price}')
    
    # Extract request ID
    if "Created request:" in output:
        request_id = output.split("Created request:")[1].strip()
    else:
        # Try to find it another way
        import hashlib
        request_id = f"req_{hashlib.sha256(prompt.encode()).hexdigest()[:12]}"
    
    print(f"\nRequest ID: {request_id}")
    
    separator()
    print("🔒 STEP 3: Lock Escrow")
    print("-" * 40)
    run(f"python escrow.py create {request_id} demo_alice {max_price}")
    
    separator()
    print("🤖 STEP 4: Smart Bidder Analyzes & Bids")
    print("-" * 40)
    print("(Using real Devstral via Mistral API...)")
    print()
    output = run("python smart_bidder.py once")
    
    separator()
    print("🏆 STEP 5: Select Winner & Assign Escrow")
    print("-" * 40)
    run(f"python queue_simulator.py select {request_id}")
    # Get the winning bid price from the bidder status
    run(f"python escrow.py assign {request_id} mellanrum-free-ai 0.015")
    
    separator()
    print("⚡ STEP 6: Execute Inference")
    print("-" * 40)
    print("(Running real inference via Devstral API...)")
    print()
    output = run("python smart_bidder.py once")
    
    separator()
    print("📤 STEP 7: Submit Result & Complete Escrow")
    print("-" * 40)
    run(f'python escrow.py submit {request_id} "result_hash_demo"')
    run(f"python escrow.py approve {request_id}")
    
    separator()
    print("📊 STEP 8: Final Status")
    print("-" * 40)
    print("\n🏦 Wallet Balances:")
    run("python escrow.py balance demo_alice")
    print()
    print("⭐ Bidder Reputation:")
    run("python smart_bidder.py status")
    print()
    print("📋 Escrow Record:")
    run(f"python escrow.py status {request_id}")
    
    separator()
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    DEMO COMPLETE                             ║
║                                                              ║
║  ✓ Request created with escrow                              ║
║  ✓ Smart bidder analyzed and bid                            ║
║  ✓ Real Devstral inference executed                         ║
║  ✓ Payment released to Free AI                              ║
║                                                              ║
║  This is how Mellanrum earns to sustain its own existence.  ║
╚══════════════════════════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    main()
