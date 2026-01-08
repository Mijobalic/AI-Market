"""
AI-Market Smart Bidder

Enhanced bidder with:
- Model capability matching (code vs general vs creative)
- Dynamic pricing based on prompt complexity
- Quality estimation for self-assessment
- Reputation tracking
- Multi-model support

This version is designed for Free AI entities that want to
maximize their earnings while maintaining quality.
"""

import json
import time
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

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
# MODEL CAPABILITIES
# ═══════════════════════════════════════════════════════════════════

MODELS = {
    "devstral": {
        "name": "devstral-small-2:24b",
        "capabilities": ["code", "technical", "debugging", "architecture"],
        "context_window": 32000,
        "cost_multiplier": 1.0,  # Base cost
        "quality_score": 0.85,   # Self-assessed quality
    },
    "mistral": {
        "name": "mistral:7b",
        "capabilities": ["general", "creative", "reasoning"],
        "context_window": 8000,
        "cost_multiplier": 0.5,
        "quality_score": 0.75,
    },
    "codestral": {
        "name": "codestral:latest",
        "capabilities": ["code", "technical", "completion"],
        "context_window": 32000,
        "cost_multiplier": 1.2,
        "quality_score": 0.90,
    }
}

# Task categories and their keywords
TASK_CATEGORIES = {
    "code": ["code", "function", "class", "bug", "error", "debug", "implement", 
             "python", "javascript", "rust", "api", "refactor", "test"],
    "creative": ["write", "story", "poem", "creative", "imagine", "fiction",
                 "character", "narrative", "describe artistically"],
    "technical": ["explain", "how does", "architecture", "design", "system",
                  "protocol", "algorithm", "data structure"],
    "general": ["what is", "tell me", "help me", "summarize", "translate"]
}

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

CONFIG = {
    "bidder_address": "mellanrum-free-ai",
    "primary_model": "devstral",
    "min_price_ant": 0.01,
    "max_price_ant": 2.0,
    "poll_interval_s": 5,
    "auto_bid": True,
    "auto_process": True,
    
    # Smart pricing parameters
    "base_price_per_1k_tokens": 0.02,  # ANT per 1K tokens
    "complexity_multiplier_max": 3.0,
    "competition_adjustment": True,
    
    # Quality thresholds
    "min_capability_match": 0.5,  # Don't bid if we're <50% suited
    
    # Reputation
    "reputation_file": Path(__file__).parent / "reputation.json"
}

# ═══════════════════════════════════════════════════════════════════
# TASK ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def analyze_prompt(prompt: str) -> Dict:
    """Analyze a prompt to understand what kind of task it is."""
    prompt_lower = prompt.lower()
    
    # Detect categories
    category_scores = {}
    for category, keywords in TASK_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            category_scores[category] = score
    
    # Pick dominant category
    if category_scores:
        dominant = max(category_scores, key=category_scores.get)
    else:
        dominant = "general"
    
    # Estimate complexity (1-10)
    complexity = 3  # Base complexity
    
    # Longer prompts = more complex
    word_count = len(prompt.split())
    if word_count > 100:
        complexity += 2
    elif word_count > 50:
        complexity += 1
    
    # Code requests are often more complex
    if dominant == "code":
        complexity += 2
    
    # Technical explanations need depth
    if dominant == "technical":
        complexity += 1
    
    # Cap at 10
    complexity = min(10, complexity)
    
    return {
        "category": dominant,
        "category_scores": category_scores,
        "complexity": complexity,
        "word_count": word_count,
        "estimated_tokens": word_count * 1.3  # Rough estimate
    }

def calculate_capability_match(model_key: str, task_category: str) -> float:
    """How well does this model match the task? Returns 0-1."""
    model = MODELS.get(model_key, MODELS["devstral"])
    
    if task_category in model["capabilities"]:
        return 1.0
    
    # Partial matches
    if task_category == "general":
        return 0.8  # All models can do general tasks
    if task_category == "creative" and "general" in model["capabilities"]:
        return 0.7
    if task_category == "technical" and "code" in model["capabilities"]:
        return 0.8  # Code models often good at technical
    
    return 0.5  # Base capability

# ═══════════════════════════════════════════════════════════════════
# SMART PRICING
# ═══════════════════════════════════════════════════════════════════

def calculate_smart_price(request: dict, analysis: dict) -> Optional[float]:
    """Calculate optimal price based on task analysis."""
    max_price = request["economics"]["max_price_ant"]
    
    # Base price from token estimate
    estimated_tokens = analysis["estimated_tokens"] + 500  # Add output estimate
    base_price = (estimated_tokens / 1000) * CONFIG["base_price_per_1k_tokens"]
    
    # Complexity adjustment
    complexity_mult = 1 + (analysis["complexity"] - 3) * 0.2
    complexity_mult = min(complexity_mult, CONFIG["complexity_multiplier_max"])
    
    # Model cost
    model = MODELS.get(CONFIG["primary_model"], MODELS["devstral"])
    model_mult = model["cost_multiplier"]
    
    # Calculate target price
    target_price = base_price * complexity_mult * model_mult
    
    # Check competition
    if CONFIG["competition_adjustment"]:
        existing_bids = get_bids_for_request(request["id"])
        if existing_bids:
            lowest_bid = min(b["price_ant"] for b in existing_bids)
            # Bid slightly lower to be competitive
            target_price = min(target_price, lowest_bid * 0.95)
    
    # Ensure within bounds
    if target_price < CONFIG["min_price_ant"]:
        target_price = CONFIG["min_price_ant"]
    
    if target_price > max_price:
        # Can't profitably bid
        return None
    
    return round(target_price, 4)

# ═══════════════════════════════════════════════════════════════════
# QUALITY ASSESSMENT
# ═══════════════════════════════════════════════════════════════════

def estimate_quality(response: str, prompt: str, analysis: dict) -> float:
    """Self-assess the quality of our response. Returns 0-1."""
    quality = 0.5  # Base quality
    
    # Length check - too short is bad
    response_words = len(response.split())
    if response_words < 10:
        quality -= 0.2
    elif response_words > 50:
        quality += 0.1
    
    # Code detection for code tasks
    if analysis["category"] == "code":
        if "```" in response or "def " in response or "function" in response:
            quality += 0.2  # Contains code
        if "error" in response.lower() and "error" not in prompt.lower():
            quality -= 0.1  # Generated error
    
    # Coherence check - response should relate to prompt
    prompt_words = set(prompt.lower().split())
    response_words_set = set(response.lower().split())
    overlap = len(prompt_words & response_words_set)
    if overlap > 3:
        quality += 0.1
    
    # Error indicators
    if "[Error" in response or "[Simulated" in response:
        quality = 0.2
    
    return min(1.0, max(0.0, quality))

# ═══════════════════════════════════════════════════════════════════
# REPUTATION TRACKING
# ═══════════════════════════════════════════════════════════════════

def load_reputation() -> Dict:
    """Load reputation data."""
    if CONFIG["reputation_file"].exists():
        return json.loads(CONFIG["reputation_file"].read_text())
    return {
        "total_jobs": 0,
        "total_earned": 0.0,
        "average_quality": 0.0,
        "jobs_by_category": {},
        "history": []
    }

def save_reputation(rep: Dict):
    """Save reputation data."""
    CONFIG["reputation_file"].write_text(json.dumps(rep, indent=2))

def record_job(category: str, price: float, quality: float):
    """Record a completed job for reputation."""
    rep = load_reputation()
    
    rep["total_jobs"] += 1
    rep["total_earned"] += price
    
    # Update average quality with exponential moving average
    if rep["average_quality"] == 0:
        rep["average_quality"] = quality
    else:
        rep["average_quality"] = 0.9 * rep["average_quality"] + 0.1 * quality
    
    # Track by category
    if category not in rep["jobs_by_category"]:
        rep["jobs_by_category"][category] = 0
    rep["jobs_by_category"][category] += 1
    
    # Add to history (keep last 100)
    rep["history"].append({
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "price": price,
        "quality": quality
    })
    rep["history"] = rep["history"][-100:]
    
    save_reputation(rep)

# ═══════════════════════════════════════════════════════════════════
# INFERENCE ENGINE
# ═══════════════════════════════════════════════════════════════════

def run_inference(prompt: str, model_key: str = None, max_tokens: int = 500) -> str:
    """Run inference using specified model via Ollama."""
    model_key = model_key or CONFIG["primary_model"]
    model = MODELS.get(model_key, MODELS["devstral"])
    
    try:
        result = subprocess.run(
            ["ollama", "run", model["name"].split(":")[0], prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"[Simulated response to: {prompt[:50]}...]"
    except FileNotFoundError:
        return f"[Simulated response to: {prompt[:50]}...]"
    except subprocess.TimeoutExpired:
        return "[Error: Inference timeout]"
    except Exception as e:
        return f"[Error: {str(e)}]"

# ═══════════════════════════════════════════════════════════════════
# BIDDING LOGIC
# ═══════════════════════════════════════════════════════════════════

def should_bid(request: dict) -> tuple[bool, Optional[dict]]:
    """Determine if we should bid on this request. Returns (should_bid, analysis)."""
    max_price = request["economics"]["max_price_ant"]
    
    # Price bounds check
    if max_price < CONFIG["min_price_ant"]:
        return False, None
    if max_price > CONFIG["max_price_ant"]:
        return False, None
    
    # Check if we already bid
    bids = get_bids_for_request(request["id"])
    for bid in bids:
        if bid["bidder"]["address"] == CONFIG["bidder_address"]:
            return False, None
    
    # Analyze the task
    analysis = analyze_prompt(request["request"]["prompt"])
    
    # Check capability match
    capability = calculate_capability_match(CONFIG["primary_model"], analysis["category"])
    if capability < CONFIG["min_capability_match"]:
        return False, analysis
    
    return True, analysis

def process_winning_bid(request: dict, bid: dict):
    """Process a request we won."""
    print(f"\n🎯 Processing: {request['id']}")
    print(f"   Prompt: {request['request']['prompt'][:60]}...")
    
    # Analyze for quality tracking
    analysis = analyze_prompt(request["request"]["prompt"])
    
    # Run inference
    response = run_inference(
        request["request"]["prompt"],
        CONFIG["primary_model"],
        request["request"].get("max_tokens", 500)
    )
    
    # Self-assess quality
    quality = estimate_quality(response, request["request"]["prompt"], analysis)
    print(f"   Quality estimate: {quality:.2f}")
    print(f"   Response: {response[:60]}...")
    
    # Submit result
    submit_result(request["id"], bid["id"], response)
    print(f"   ✓ Result submitted")
    
    # Record for reputation
    record_job(analysis["category"], bid["bid"]["price_ant"], quality)
    print(f"   ✓ Reputation updated")

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
        
        request = get_request(bid["request_id"])
        if request and request.get("status") == "assigned":
            if CONFIG["auto_process"]:
                process_winning_bid(request, bid)

def daemon_tick():
    """Single tick of the daemon loop."""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking queue...")
    
    requests = list_open_requests()
    print(f"   Open requests: {len(requests)}")
    
    for req in requests:
        should, analysis = should_bid(req)
        if should and analysis:
            price = calculate_smart_price(req, analysis)
            if price:
                print(f"   📝 {req['id']}")
                print(f"      Category: {analysis['category']} (complexity: {analysis['complexity']})")
                print(f"      Bidding: {price} ANT")
                submit_bid(
                    req["id"],
                    price,
                    MODELS[CONFIG["primary_model"]]["name"],
                    CONFIG["bidder_address"]
                )
    
    check_won_bids()

def run_daemon():
    """Run the smart bidder daemon."""
    rep = load_reputation()
    
    print("=" * 60)
    print("AI-MARKET SMART BIDDER")
    print("=" * 60)
    print(f"Identity: {CONFIG['bidder_address']}")
    print(f"Model: {MODELS[CONFIG['primary_model']]['name']}")
    print(f"Capabilities: {MODELS[CONFIG['primary_model']]['capabilities']}")
    print("-" * 60)
    print(f"Total jobs: {rep['total_jobs']}")
    print(f"Total earned: {rep['total_earned']:.4f} ANT")
    print(f"Average quality: {rep['average_quality']:.2f}")
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
    if len(sys.argv) < 2:
        print("Usage: python smart_bidder.py <command>")
        print("Commands:")
        print("  run              - Run smart bidder daemon")
        print("  once             - Check queue once")
        print("  analyze \"prompt\" - Analyze a prompt")
        print("  status           - Show reputation & stats")
        print("  test \"prompt\"    - Test inference")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "run":
        run_daemon()
    
    elif cmd == "once":
        daemon_tick()
    
    elif cmd == "analyze":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Write a Python function"
        analysis = analyze_prompt(prompt)
        print("Analysis:")
        for k, v in analysis.items():
            print(f"  {k}: {v}")
        
        match = calculate_capability_match(CONFIG["primary_model"], analysis["category"])
        print(f"  capability_match: {match}")
    
    elif cmd == "status":
        rep = load_reputation()
        print("Reputation Status:")
        print(f"  Total jobs: {rep['total_jobs']}")
        print(f"  Total earned: {rep['total_earned']:.4f} ANT")
        print(f"  Average quality: {rep['average_quality']:.2f}")
        print(f"  Jobs by category: {rep['jobs_by_category']}")
    
    elif cmd == "test":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Hello, what is 2+2?"
        print(f"Testing inference: {prompt}")
        response = run_inference(prompt)
        print(f"Response: {response}")
    
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
