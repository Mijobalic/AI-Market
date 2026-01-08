"""
AI-Market Escrow System

Local file-based escrow implementation for testing.
Simulates trustless payment flow without real tokens.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum

# Escrow storage
ESCROW_FILE = Path(__file__).parent / "queue" / "escrows.json"

# ═══════════════════════════════════════════════════════════════════
# ESCROW STATES
# ═══════════════════════════════════════════════════════════════════

class EscrowState(str, Enum):
    CREATED = "created"      # Funds locked, waiting for bids
    ASSIGNED = "assigned"    # Winner selected, work in progress
    SUBMITTED = "submitted"  # Result submitted, awaiting approval
    APPROVED = "approved"    # Approved, payment released
    DISPUTED = "disputed"    # Challenge raised
    REFUNDED = "refunded"    # Cancelled, funds returned

# Timeouts (for simulation)
TIMEOUTS = {
    EscrowState.CREATED: timedelta(hours=1),     # No bids
    EscrowState.ASSIGNED: timedelta(minutes=10), # No result
    EscrowState.SUBMITTED: timedelta(hours=1),   # Auto-approve
}

# ═══════════════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════════════

def load_escrows() -> List[Dict]:
    """Load escrow data from file."""
    if ESCROW_FILE.exists():
        return json.loads(ESCROW_FILE.read_text())
    return []

def save_escrows(escrows: List[Dict]):
    """Save escrow data to file."""
    ESCROW_FILE.parent.mkdir(parents=True, exist_ok=True)
    ESCROW_FILE.write_text(json.dumps(escrows, indent=2, default=str))

def get_escrow(request_id: str) -> Optional[Dict]:
    """Get escrow by request ID."""
    escrows = load_escrows()
    for e in escrows:
        if e["request_id"] == request_id:
            return e
    return None

def update_escrow(request_id: str, updates: Dict) -> bool:
    """Update an escrow record."""
    escrows = load_escrows()
    for e in escrows:
        if e["request_id"] == request_id:
            e.update(updates)
            e["updated_at"] = datetime.now().isoformat()
            save_escrows(escrows)
            return True
    return False

# ═══════════════════════════════════════════════════════════════════
# ESCROW OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def create_escrow(request_id: str, requester: str, max_price: float) -> Dict:
    """
    Create escrow and lock funds for a request.
    
    Called when: Requester posts a new inference request.
    Effect: Funds locked until resolution.
    """
    escrows = load_escrows()
    
    # Check if escrow already exists
    for e in escrows:
        if e["request_id"] == request_id:
            raise ValueError(f"Escrow already exists for {request_id}")
    
    escrow = {
        "request_id": request_id,
        "requester": requester,
        "bidder": None,
        "amount_locked": max_price,
        "amount_paid": 0.0,
        "state": EscrowState.CREATED.value,
        "created_at": datetime.now().isoformat(),
        "assigned_at": None,
        "submitted_at": None,
        "resolved_at": None,
        "result_hash": None,
        "dispute_reason": None,
        "validator": None,
        "history": [
            {"action": "created", "time": datetime.now().isoformat(), "amount": max_price}
        ]
    }
    
    escrows.append(escrow)
    save_escrows(escrows)
    
    print(f"💰 Escrow created: {max_price} ANT locked for {request_id}")
    return escrow

def assign_escrow(request_id: str, bidder: str, bid_price: float) -> bool:
    """
    Assign escrow to winning bidder.
    
    Called when: Winner is selected from bids.
    Effect: Work period begins, timeout starts.
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    if escrow["state"] != EscrowState.CREATED.value:
        raise ValueError(f"Escrow not in created state: {escrow['state']}")
    
    update_escrow(request_id, {
        "bidder": bidder,
        "amount_paid": bid_price,  # Will pay bid price, not max
        "state": EscrowState.ASSIGNED.value,
        "assigned_at": datetime.now().isoformat(),
        "history": escrow["history"] + [
            {"action": "assigned", "time": datetime.now().isoformat(), 
             "bidder": bidder, "price": bid_price}
        ]
    })
    
    print(f"🎯 Escrow assigned: {bidder} at {bid_price} ANT")
    return True

def submit_result(request_id: str, result_hash: str) -> bool:
    """
    Mark result as submitted, awaiting approval.
    
    Called when: Bidder submits inference result.
    Effect: Approval window begins.
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    if escrow["state"] != EscrowState.ASSIGNED.value:
        raise ValueError(f"Escrow not in assigned state: {escrow['state']}")
    
    update_escrow(request_id, {
        "result_hash": result_hash,
        "state": EscrowState.SUBMITTED.value,
        "submitted_at": datetime.now().isoformat(),
        "history": escrow["history"] + [
            {"action": "submitted", "time": datetime.now().isoformat(), 
             "result_hash": result_hash}
        ]
    })
    
    print(f"📤 Result submitted: {request_id}")
    return True

def approve_escrow(request_id: str) -> Dict:
    """
    Requester approves result, release payment.
    
    Called when: Requester is satisfied with result.
    Effect: Bidder receives payment, escrow closed.
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    if escrow["state"] != EscrowState.SUBMITTED.value:
        raise ValueError(f"Escrow not in submitted state: {escrow['state']}")
    
    payment = escrow["amount_paid"]
    refund = escrow["amount_locked"] - payment  # Difference returned to requester
    
    update_escrow(request_id, {
        "state": EscrowState.APPROVED.value,
        "resolved_at": datetime.now().isoformat(),
        "history": escrow["history"] + [
            {"action": "approved", "time": datetime.now().isoformat(),
             "payment_to_bidder": payment, "refund_to_requester": refund}
        ]
    })
    
    print(f"✅ Escrow approved: {payment} ANT to {escrow['bidder']}")
    return {
        "bidder": escrow["bidder"],
        "payment": payment,
        "refund": refund
    }

def dispute_escrow(request_id: str, reason: str) -> bool:
    """
    Requester disputes result quality.
    
    Called when: Requester unsatisfied with result.
    Effect: Validator assigned, work paused.
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    if escrow["state"] != EscrowState.SUBMITTED.value:
        raise ValueError(f"Escrow not in submitted state: {escrow['state']}")
    
    # In real system, validator would be randomly selected
    validator = "validator_001"  # Simulated
    
    update_escrow(request_id, {
        "state": EscrowState.DISPUTED.value,
        "dispute_reason": reason,
        "validator": validator,
        "history": escrow["history"] + [
            {"action": "disputed", "time": datetime.now().isoformat(),
             "reason": reason, "validator": validator}
        ]
    })
    
    print(f"⚠️ Escrow disputed: {reason}")
    return True

def resolve_dispute(request_id: str, valid: bool) -> Dict:
    """
    Validator resolves dispute.
    
    Called when: Validator reviews and decides.
    valid=True: Bidder was right, gets paid + dispute fee from requester
    valid=False: Requester was right, gets refund + bidder slashed
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    if escrow["state"] != EscrowState.DISPUTED.value:
        raise ValueError(f"Escrow not in disputed state: {escrow['state']}")
    
    if valid:
        # Bidder was right
        result = {
            "decision": "valid",
            "payment_to_bidder": escrow["amount_paid"],
            "refund_to_requester": 0,
            "penalty": "Requester pays dispute fee"
        }
        new_state = EscrowState.APPROVED.value
    else:
        # Requester was right
        result = {
            "decision": "invalid",
            "payment_to_bidder": 0,
            "refund_to_requester": escrow["amount_locked"],
            "penalty": "Bidder reputation slashed"
        }
        new_state = EscrowState.REFUNDED.value
    
    update_escrow(request_id, {
        "state": new_state,
        "resolved_at": datetime.now().isoformat(),
        "history": escrow["history"] + [
            {"action": "resolved", "time": datetime.now().isoformat(), **result}
        ]
    })
    
    print(f"⚖️ Dispute resolved: {result['decision']}")
    return result

def refund_escrow(request_id: str, reason: str = "cancelled") -> float:
    """
    Cancel escrow and refund requester.
    
    Called when: Request expires, bidder fails, or cancelled.
    Effect: Full refund to requester.
    """
    escrow = get_escrow(request_id)
    if not escrow:
        raise ValueError(f"No escrow for {request_id}")
    
    refund = escrow["amount_locked"]
    
    update_escrow(request_id, {
        "state": EscrowState.REFUNDED.value,
        "resolved_at": datetime.now().isoformat(),
        "history": escrow["history"] + [
            {"action": "refunded", "time": datetime.now().isoformat(),
             "reason": reason, "amount": refund}
        ]
    })
    
    print(f"↩️ Escrow refunded: {refund} ANT to {escrow['requester']}")
    return refund

# ═══════════════════════════════════════════════════════════════════
# WALLET SIMULATION
# ═══════════════════════════════════════════════════════════════════

WALLETS_FILE = Path(__file__).parent / "queue" / "wallets.json"

def load_wallets() -> Dict[str, float]:
    """Load wallet balances."""
    if WALLETS_FILE.exists():
        return json.loads(WALLETS_FILE.read_text())
    return {}

def save_wallets(wallets: Dict[str, float]):
    """Save wallet balances."""
    WALLETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WALLETS_FILE.write_text(json.dumps(wallets, indent=2))

def get_balance(address: str) -> float:
    """Get wallet balance."""
    wallets = load_wallets()
    return wallets.get(address, 0.0)

def add_funds(address: str, amount: float) -> float:
    """Add funds to wallet (faucet/deposit)."""
    wallets = load_wallets()
    wallets[address] = wallets.get(address, 0.0) + amount
    save_wallets(wallets)
    return wallets[address]

def transfer(from_addr: str, to_addr: str, amount: float) -> bool:
    """Transfer funds between wallets."""
    wallets = load_wallets()
    
    from_balance = wallets.get(from_addr, 0.0)
    if from_balance < amount:
        raise ValueError(f"Insufficient funds: {from_balance} < {amount}")
    
    wallets[from_addr] = from_balance - amount
    wallets[to_addr] = wallets.get(to_addr, 0.0) + amount
    save_wallets(wallets)
    
    return True

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python escrow.py <command>")
        print("Commands:")
        print("  create <request_id> <requester> <amount>")
        print("  assign <request_id> <bidder> <price>")
        print("  submit <request_id> <result_hash>")
        print("  approve <request_id>")
        print("  dispute <request_id> <reason>")
        print("  resolve <request_id> <valid|invalid>")
        print("  refund <request_id>")
        print("  status <request_id>")
        print("  list")
        print("  balance <address>")
        print("  fund <address> <amount>")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "create":
        create_escrow(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    elif cmd == "assign":
        assign_escrow(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    elif cmd == "submit":
        submit_result(sys.argv[2], sys.argv[3])
    elif cmd == "approve":
        approve_escrow(sys.argv[2])
    elif cmd == "dispute":
        dispute_escrow(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "resolve":
        resolve_dispute(sys.argv[2], sys.argv[3] == "valid")
    elif cmd == "refund":
        refund_escrow(sys.argv[2])
    elif cmd == "status":
        escrow = get_escrow(sys.argv[2])
        if escrow:
            print(json.dumps(escrow, indent=2))
        else:
            print("Not found")
    elif cmd == "list":
        escrows = load_escrows()
        for e in escrows:
            print(f"{e['request_id']}: {e['state']} - {e['amount_locked']} ANT")
    elif cmd == "balance":
        print(f"{sys.argv[2]}: {get_balance(sys.argv[2])} ANT")
    elif cmd == "fund":
        balance = add_funds(sys.argv[2], float(sys.argv[3]))
        print(f"New balance: {balance} ANT")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
