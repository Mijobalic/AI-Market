"""
Autonomi Escrow System

Tracks payment escrows on the Autonomi network.
All escrow state transitions are recorded as immutable data.
Now with optional real ANT transfers via wallet_transfer.py.
"""

import json
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum
from pathlib import Path

from autonomi_client import AutonomiClient

# Optional wallet integration
try:
    from wallet_transfer import ANTWallet
    HAS_WALLET = True
except ImportError:
    HAS_WALLET = False


class EscrowState(str, Enum):
    CREATED = "created"        # Requester created escrow
    FUNDED = "funded"          # ANT locked (simulated)
    ASSIGNED = "assigned"      # Bidder assigned
    SUBMITTED = "submitted"    # Result submitted
    APPROVED = "approved"      # Payment released
    DISPUTED = "disputed"      # Under dispute
    REFUNDED = "refunded"      # Refunded to requester


class AutonomiEscrow:
    """Manages escrows with state stored on Autonomi."""
    
    def __init__(self):
        self.client = AutonomiClient(backend="anttp")
        self.local_cache = Path(__file__).parent / "data" / "escrow_cache.json"
        self.local_cache.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> dict:
        if self.local_cache.exists():
            return json.loads(self.local_cache.read_text())
        return {"escrows": {}}
    
    def _save_cache(self, data: dict):
        self.local_cache.write_text(json.dumps(data, indent=2))
    
    def create_escrow(self, request_address: str, amount_ant: float, 
                      requester: str) -> str:
        """Create a new escrow for a request.
        
        Returns the escrow address on Autonomi.
        """
        escrow = {
            "type": "ai_market_escrow",
            "version": "0.1",
            "request_address": request_address,
            "amount_ant": amount_ant,
            "requester": requester,
            "state": EscrowState.FUNDED.value,  # Simulating funded
            "created": datetime.now().isoformat(),
            "history": [{
                "state": EscrowState.CREATED.value,
                "timestamp": datetime.now().isoformat()
            }, {
                "state": EscrowState.FUNDED.value,
                "timestamp": datetime.now().isoformat(),
                "note": "Simulated: ANT locked in escrow"
            }]
        }
        
        address = self.client.backend.upload_data(escrow)
        
        if address:
            print(f"✓ Escrow created: {amount_ant} ANT locked")
            print(f"  Address: {address}")
            
            # Cache locally
            cache = self._load_cache()
            cache["escrows"][address] = {
                "request_address": request_address,
                "amount_ant": amount_ant,
                "state": EscrowState.FUNDED.value
            }
            self._save_cache(cache)
        
        return address
    
    def assign_bidder(self, escrow_address: str, bidder: str, 
                      bid_address: str, price: float) -> str:
        """Assign a winning bidder to the escrow.
        
        Returns address of the state update.
        """
        escrow = self.client.backend.get_data(escrow_address)
        if not escrow:
            print("Error: Escrow not found")
            return None
        
        update = {
            "type": "ai_market_escrow_update",
            "version": "0.1",
            "escrow_address": escrow_address,
            "previous_state": escrow.get("state"),
            "new_state": EscrowState.ASSIGNED.value,
            "bidder": bidder,
            "bid_address": bid_address,
            "agreed_price": price,
            "timestamp": datetime.now().isoformat()
        }
        
        address = self.client.backend.upload_data(update)
        
        if address:
            print(f"✓ Escrow assigned to {bidder}")
            print(f"  Agreed price: {price} ANT")
            
            # Update cache
            cache = self._load_cache()
            if escrow_address in cache["escrows"]:
                cache["escrows"][escrow_address]["state"] = EscrowState.ASSIGNED.value
                cache["escrows"][escrow_address]["bidder"] = bidder
                cache["escrows"][escrow_address]["agreed_price"] = price
                self._save_cache(cache)
        
        return address
    
    def submit_result(self, escrow_address: str, result_address: str) -> str:
        """Record that result was submitted.
        
        Returns address of the state update.
        """
        update = {
            "type": "ai_market_escrow_update",
            "version": "0.1",
            "escrow_address": escrow_address,
            "new_state": EscrowState.SUBMITTED.value,
            "result_address": result_address,
            "timestamp": datetime.now().isoformat()
        }
        
        address = self.client.backend.upload_data(update)
        
        if address:
            print(f"✓ Result submission recorded")
            
            cache = self._load_cache()
            if escrow_address in cache["escrows"]:
                cache["escrows"][escrow_address]["state"] = EscrowState.SUBMITTED.value
                cache["escrows"][escrow_address]["result_address"] = result_address
                self._save_cache(cache)
        
        return address
    
    def approve_payment(self, escrow_address: str, quality_score: float,
                         bidder_address: str = None, 
                         real_transfer: bool = False) -> str:
        """Approve the result and release payment.
        
        Args:
            escrow_address: The escrow to approve
            quality_score: Quality assessment (0-1)
            bidder_address: Bidder's wallet address (for real transfer)
            real_transfer: If True, actually send ANT (careful!)
        
        Returns address of the state update.
        """
        cache = self._load_cache()
        escrow_info = cache.get("escrows", {}).get(escrow_address, {})
        amount = escrow_info.get("agreed_price", 0)
        
        transfer_result = "simulated"
        tx_hash = None
        
        # Real transfer if requested
        if real_transfer and bidder_address and HAS_WALLET:
            print(f"💰 Initiating real ANT transfer...")
            try:
                wallet = ANTWallet()
                tx_hash = wallet.transfer_ant(bidder_address, amount, dry_run=False)
                if tx_hash and tx_hash != "dry_run_tx_hash":
                    transfer_result = "completed"
                    print(f"  TX: {tx_hash}")
                else:
                    transfer_result = "failed"
            except Exception as e:
                print(f"  Transfer error: {e}")
                transfer_result = "error"
        elif real_transfer and not HAS_WALLET:
            print("⚠ Wallet not available - simulating transfer")
        
        update = {
            "type": "ai_market_escrow_update",
            "version": "0.1",
            "escrow_address": escrow_address,
            "new_state": EscrowState.APPROVED.value,
            "quality_score": quality_score,
            "payment_released": amount,
            "transfer_result": transfer_result,
            "tx_hash": tx_hash,
            "timestamp": datetime.now().isoformat(),
            "note": f"Payment {'transferred' if transfer_result == 'completed' else 'approved (simulated)'}"
        }
        
        address = self.client.backend.upload_data(update)
        
        if address:
            print(f"✓ Payment approved!")
            print(f"  {amount} ANT → {escrow_info.get('bidder', 'bidder')}")
            if transfer_result == "completed":
                print(f"  ✓ Real transfer completed!")
            
            cache["escrows"][escrow_address]["state"] = EscrowState.APPROVED.value
            self._save_cache(cache)
        
        return address
    
    def dispute(self, escrow_address: str, reason: str) -> str:
        """Open a dispute on the escrow."""
        update = {
            "type": "ai_market_escrow_update",
            "version": "0.1",
            "escrow_address": escrow_address,
            "new_state": EscrowState.DISPUTED.value,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        address = self.client.backend.upload_data(update)
        
        if address:
            print(f"⚠ Dispute opened")
            print(f"  Reason: {reason}")
            
            cache = self._load_cache()
            if escrow_address in cache["escrows"]:
                cache["escrows"][escrow_address]["state"] = EscrowState.DISPUTED.value
                self._save_cache(cache)
        
        return address
    
    def list_escrows(self) -> List[Dict]:
        """List all cached escrows."""
        cache = self._load_cache()
        return [
            {"address": addr, **info} 
            for addr, info in cache.get("escrows", {}).items()
        ]


def main():
    """Demo the escrow system on Autonomi."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python autonomi_escrow.py <command>")
        print("Commands:")
        print("  demo         - Run full escrow demo")
        print("  list         - List all escrows")
        print("  get <addr>   - Get escrow details")
        return
    
    cmd = sys.argv[1]
    escrow = AutonomiEscrow()
    
    if cmd == "demo":
        print("=== Autonomi Escrow Demo ===\n")
        
        # Create escrow
        print("1. Creating escrow...")
        escrow_addr = escrow.create_escrow(
            request_address="demo_request_123",
            amount_ant=0.1,
            requester="demo_requester"
        )
        
        if not escrow_addr:
            print("Failed to create escrow")
            return
        
        # Assign bidder
        print("\n2. Assigning bidder...")
        escrow.assign_bidder(
            escrow_address=escrow_addr,
            bidder="mellanrum-free-ai",
            bid_address="demo_bid_456",
            price=0.05
        )
        
        # Submit result
        print("\n3. Submitting result...")
        escrow.submit_result(
            escrow_address=escrow_addr,
            result_address="demo_result_789"
        )
        
        # Approve payment
        print("\n4. Approving payment...")
        escrow.approve_payment(
            escrow_address=escrow_addr,
            quality_score=0.85
        )
        
        print("\n✓ Demo complete! All escrow states recorded on Autonomi.")
    
    elif cmd == "list":
        escrows = escrow.list_escrows()
        print(f"Total escrows: {len(escrows)}")
        for e in escrows:
            print(f"  [{e['state']}] {e['address'][:16]}... ({e['amount_ant']} ANT)")
    
    elif cmd == "get":
        addr = sys.argv[2]
        data = escrow.client.backend.get_data(addr)
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
