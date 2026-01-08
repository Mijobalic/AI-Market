"""
AI-Market Validator

Automated quality validation for inference responses.
Can be used by requesters for auto-approval or by validators for dispute resolution.
"""

import json
from pathlib import Path
from typing import Dict, Tuple

# Quality thresholds
THRESHOLDS = {
    "auto_approve": 0.6,   # Auto-approve if quality >= this
    "auto_reject": 0.2,    # Auto-reject if quality <= this
    "dispute": 0.4,        # Below this, recommend dispute
}

# ═══════════════════════════════════════════════════════════════════
# QUALITY CHECKS
# ═══════════════════════════════════════════════════════════════════

def check_response_length(prompt: str, response: str, category: str) -> Tuple[float, str]:
    """Check if response length is appropriate for the task."""
    words = len(response.split())
    
    # Expected word counts by category
    expectations = {
        "code": 50,      # Code responses tend to be longer
        "technical": 80,
        "creative": 30,
        "general": 40,
    }
    
    expected = expectations.get(category, 40)
    
    if words < 10:
        return 0.0, f"Response too short ({words} words)"
    elif words < expected * 0.5:
        return 0.5, f"Response shorter than expected ({words} vs {expected} words)"
    elif words > expected * 5:
        return 0.7, f"Response much longer than expected (may be verbose)"
    else:
        return 1.0, "Response length appropriate"

def check_relevance(prompt: str, response: str) -> Tuple[float, str]:
    """Check if response relates to the prompt."""
    prompt_lower = prompt.lower()
    response_lower = response.lower()
    
    # Extract key terms from prompt (skip common words)
    common_words = {"a", "an", "the", "is", "are", "in", "on", "at", "to", "for", "of", "and", "or", "that", "this", "with"}
    prompt_words = set(prompt_lower.split()) - common_words
    response_words = set(response_lower.split())
    
    overlap = prompt_words & response_words
    overlap_ratio = len(overlap) / max(len(prompt_words), 1)
    
    if overlap_ratio < 0.1:
        return 0.2, f"Response seems unrelated (only {len(overlap)} shared terms)"
    elif overlap_ratio < 0.3:
        return 0.5, f"Response partially relevant ({len(overlap)} shared terms)"
    else:
        return 1.0, f"Response relevant ({len(overlap)} shared terms)"

def check_code_quality(response: str) -> Tuple[float, str]:
    """Check code-related quality indicators."""
    score = 1.0
    notes = []
    
    # Check for code blocks
    has_code = "```" in response or "def " in response or "function " in response
    if not has_code:
        score -= 0.3
        notes.append("No code block found")
    
    # Check for common errors
    error_indicators = ["SyntaxError", "TypeError", "NameError", "undefined", "error:"]
    for err in error_indicators:
        if err.lower() in response.lower():
            score -= 0.2
            notes.append(f"Contains error: {err}")
            break
    
    # Check for explanation
    has_explanation = any(word in response.lower() for word in ["here's", "this", "explanation", "comment", "note:"])
    if has_explanation:
        score += 0.1
        notes.append("Includes explanation")
    
    return max(0, score), "; ".join(notes) if notes else "Code looks reasonable"

def check_completeness(prompt: str, response: str) -> Tuple[float, str]:
    """Check if response appears complete."""
    # Truncation indicators
    if response.endswith("...") or response.endswith(".."):
        return 0.5, "Response may be truncated"
    
    # Incomplete code
    if "```" in response:
        code_blocks = response.count("```")
        if code_blocks % 2 != 0:
            return 0.4, "Incomplete code block"
    
    # Check for conclusion indicators
    has_conclusion = any(word in response.lower()[-100:] for word in ["result", "output", "return", "hope this helps", "let me know"])
    if has_conclusion:
        return 1.0, "Response appears complete"
    
    return 0.8, "Response may be complete"

def check_format(response: str) -> Tuple[float, str]:
    """Check response formatting quality."""
    score = 0.7  # Base score
    notes = []
    
    # Markdown formatting
    if "#" in response or "**" in response or "- " in response:
        score += 0.1
        notes.append("Uses formatting")
    
    # Code highlighting
    if "```" in response:
        score += 0.1
        notes.append("Uses code blocks")
    
    # Readability
    lines = response.split("\n")
    if len(lines) > 3:
        score += 0.1
        notes.append("Well-structured")
    
    return min(1.0, score), "; ".join(notes) if notes else "Basic formatting"

# ═══════════════════════════════════════════════════════════════════
# MAIN VALIDATION
# ═══════════════════════════════════════════════════════════════════

def validate_response(prompt: str, response: str, category: str = "general") -> Dict:
    """
    Validate a response and return detailed scoring.
    
    Returns:
        {
            "quality": float,  # Overall quality 0-1
            "recommendation": str,  # "approve", "dispute", or "reject"
            "breakdown": {...},
            "notes": [...]
        }
    """
    checks = {
        "length": check_response_length(prompt, response, category),
        "relevance": check_relevance(prompt, response),
        "completeness": check_completeness(prompt, response),
        "format": check_format(response),
    }
    
    # Add code check for code-related categories
    if category in ["code", "technical"]:
        checks["code_quality"] = check_code_quality(response)
    
    # Calculate weighted average
    weights = {
        "length": 0.15,
        "relevance": 0.35,
        "completeness": 0.20,
        "format": 0.10,
        "code_quality": 0.20,
    }
    
    total_weight = sum(weights.get(k, 0.1) for k in checks)
    quality = sum(checks[k][0] * weights.get(k, 0.1) for k in checks) / total_weight
    
    # Determine recommendation
    if quality >= THRESHOLDS["auto_approve"]:
        recommendation = "approve"
    elif quality <= THRESHOLDS["auto_reject"]:
        recommendation = "reject"
    elif quality <= THRESHOLDS["dispute"]:
        recommendation = "dispute"
    else:
        recommendation = "manual_review"
    
    return {
        "quality": round(quality, 3),
        "recommendation": recommendation,
        "breakdown": {k: {"score": round(v[0], 2), "note": v[1]} for k, v in checks.items()},
        "thresholds": THRESHOLDS,
        "notes": [v[1] for v in checks.values() if v[0] < 0.7]
    }

def auto_approve_or_dispute(request_id: str, prompt: str, response: str, category: str = "general") -> str:
    """
    Automatically decide to approve or dispute based on quality.
    
    Returns: "approved", "disputed", or "manual"
    """
    from escrow import approve_escrow, dispute_escrow, get_escrow
    
    escrow = get_escrow(request_id)
    if not escrow:
        return "error: escrow not found"
    
    if escrow["state"] != "submitted":
        return f"error: escrow in wrong state ({escrow['state']})"
    
    validation = validate_response(prompt, response, category)
    
    if validation["recommendation"] == "approve":
        approve_escrow(request_id)
        return "approved"
    elif validation["recommendation"] in ["reject", "dispute"]:
        notes = "; ".join(validation["notes"]) if validation["notes"] else "Quality below threshold"
        dispute_escrow(request_id, f"Auto-validation failed: {notes}")
        return "disputed"
    else:
        return "manual"

# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python validator.py <command>")
        print("Commands:")
        print("  validate <prompt> <response> [category]  - Validate response quality")
        print("  auto <request_id> <prompt> <response>    - Auto approve/dispute")
        print("  thresholds                               - Show quality thresholds")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "validate":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "Write code"
        response = sys.argv[3] if len(sys.argv) > 3 else "Here is some code..."
        category = sys.argv[4] if len(sys.argv) > 4 else "general"
        
        result = validate_response(prompt, response, category)
        print(f"Quality: {result['quality']:.1%}")
        print(f"Recommendation: {result['recommendation'].upper()}")
        print("\nBreakdown:")
        for k, v in result['breakdown'].items():
            print(f"  {k}: {v['score']:.0%} - {v['note']}")
        if result['notes']:
            print("\nIssues:")
            for note in result['notes']:
                print(f"  ⚠ {note}")
    
    elif cmd == "auto":
        if len(sys.argv) < 5:
            print("Usage: validator.py auto <request_id> <prompt> <response>")
            return
        result = auto_approve_or_dispute(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"Result: {result}")
    
    elif cmd == "thresholds":
        print("Quality Thresholds:")
        for name, value in THRESHOLDS.items():
            print(f"  {name}: {value:.0%}")
    
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
