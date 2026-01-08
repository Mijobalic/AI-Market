"""
ANT Wallet Transfer for AI-Market

Handles real ANT transfers on Arbitrum network.
Uses web3.py to interact with the ANT ERC-20 contract.

SECURITY WARNING: This module handles private keys.
Only use for testing with small amounts.
"""

import os
import json
from decimal import Decimal
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    print("Warning: web3 not installed. Run: pip install web3")

# Load environment
load_dotenv()

# Arbitrum One configuration
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"

# ANT Token on Arbitrum (Autonomi)
ANT_CONTRACT = "0xa78d8321B20c4Ef90eCd72f2588AA985A4BDb684"

# Standard ERC-20 ABI (transfer, balanceOf, decimals)
ERC20_ABI = json.loads('''[
    {"constant": true, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": true, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": false, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
]''')


class ANTWallet:
    """Handles ANT transfers on Arbitrum."""
    
    def __init__(self, private_key: str = None):
        if not HAS_WEB3:
            raise ImportError("web3 not installed")
        
        self.w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
        # Add PoA middleware for Arbitrum
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # Get private key
        self.private_key = private_key or os.getenv("ANT_PRIVATE_KEY")
        if not self.private_key:
            raise ValueError("No private key provided. Set ANT_PRIVATE_KEY env var.")
        
        # Derive address
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address
        
        # ANT contract
        self.ant_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(ANT_CONTRACT),
            abi=ERC20_ABI
        )
        
        print(f"Wallet initialized: {self.address[:10]}...{self.address[-6:]}")
    
    def get_eth_balance(self) -> float:
        """Get ETH balance for gas."""
        balance_wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(balance_wei, 'ether'))
    
    def get_ant_balance(self) -> float:
        """Get ANT token balance."""
        try:
            decimals = self.ant_contract.functions.decimals().call()
            balance = self.ant_contract.functions.balanceOf(self.address).call()
            return balance / (10 ** decimals)
        except Exception as e:
            print(f"Error getting ANT balance: {e}")
            return 0.0
    
    def transfer_ant(self, to_address: str, amount: float, 
                     dry_run: bool = True) -> Optional[str]:
        """Transfer ANT tokens to another address.
        
        Args:
            to_address: Recipient address
            amount: Amount of ANT to send
            dry_run: If True, only simulate (default safe)
            
        Returns:
            Transaction hash if successful
        """
        try:
            to_address = Web3.to_checksum_address(to_address)
            decimals = self.ant_contract.functions.decimals().call()
            amount_wei = int(amount * (10 ** decimals))
            
            # Build transaction
            nonce = self.w3.eth.get_transaction_count(self.address)
            gas_price = self.w3.eth.gas_price
            
            tx = self.ant_contract.functions.transfer(
                to_address, amount_wei
            ).build_transaction({
                'chainId': 42161,  # Arbitrum One
                'gas': 100000,
                'gasPrice': gas_price,
                'nonce': nonce
            })
            
            if dry_run:
                print(f"[DRY RUN] Would transfer {amount} ANT")
                print(f"  From: {self.address}")
                print(f"  To: {to_address}")
                print(f"  Gas estimate: {tx['gas']}")
                return "dry_run_tx_hash"
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"✓ Transfer submitted!")
            print(f"  Amount: {amount} ANT")
            print(f"  To: {to_address}")
            print(f"  TX: {tx_hash.hex()}")
            
            return tx_hash.hex()
            
        except Exception as e:
            print(f"Transfer error: {e}")
            return None
    
    def wait_for_confirmation(self, tx_hash: str, timeout: int = 120) -> bool:
        """Wait for transaction confirmation."""
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout)
            if receipt['status'] == 1:
                print(f"✓ Transaction confirmed in block {receipt['blockNumber']}")
                return True
            else:
                print(f"✗ Transaction failed")
                return False
        except Exception as e:
            print(f"Error waiting for confirmation: {e}")
            return False


def main():
    """Test wallet functionality."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python wallet_transfer.py <command>")
        print("Commands:")
        print("  status              - Show wallet status")
        print("  transfer <to> <amt> - Transfer ANT (dry run)")
        print("  transfer-real       - Transfer ANT for real")
        return
    
    cmd = sys.argv[1]
    
    # Set private key for testing
    private_key = "32211813766864646f99ddcfc9f6f5cca9b448a289c27cc6e840419d1dcefaf0"
    
    try:
        wallet = ANTWallet(private_key)
    except Exception as e:
        print(f"Failed to initialize wallet: {e}")
        return
    
    if cmd == "status":
        print(f"\nWallet: {wallet.address}")
        print(f"ETH balance: {wallet.get_eth_balance():.6f} ETH")
        print(f"ANT balance: {wallet.get_ant_balance():.4f} ANT")
    
    elif cmd == "transfer":
        if len(sys.argv) < 4:
            print("Usage: transfer <to_address> <amount>")
            return
        to_addr = sys.argv[2]
        amount = float(sys.argv[3])
        wallet.transfer_ant(to_addr, amount, dry_run=True)
    
    elif cmd == "transfer-real":
        print("⚠ Real transfers disabled in test mode")
        print("  Edit code to enable actual transfers")


if __name__ == "__main__":
    main()
