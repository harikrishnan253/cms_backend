"""
Token Counting Verification Script
Run this to verify that Gemini API token counting is accurate.

IMPORTANT: Gemini 2.5 models include "thinking tokens" that are:
- Billed at output token rates
- NOT included in candidates_token_count
- INCLUDED in total_token_count
- This causes total > input + output
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_token_counting():
    """Test token counting with a small sample."""

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        print("ERROR: Set GOOGLE_API_KEY environment variable")
        return False

    from google import genai
    from google.genai import types

    print("=" * 60)
    print("TOKEN COUNTING VERIFICATION TEST")
    print("=" * 60)

    # Create client
    client = genai.Client(api_key=api_key)

    # Configure generation
    generation_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
    )
    
    # Test prompt
    test_prompt = """Classify these paragraphs:
[1] CHAPTER 5
[2] Introduction to Machine Learning
[3] This chapter covers the basics of ML.

Return JSON array: [{"id": 1, "tag": "CN"}, ...]"""

    print(f"\nTest Prompt ({len(test_prompt)} chars):")
    print("-" * 40)
    print(test_prompt[:200] + "..." if len(test_prompt) > 200 else test_prompt)
    print("-" * 40)

    # Make API call
    print("\nCalling Gemini API...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=types.Content(
            role="user",
            parts=[types.Part(text=test_prompt)]
        ),
        config=generation_config
    )
    
    # Check response
    print("\nResponse received!")
    print(f"Response text: {response.text[:200]}...")
    
    # Check token usage
    print("\n" + "=" * 60)
    print("TOKEN USAGE ANALYSIS")
    print("=" * 60)
    
    if hasattr(response, 'usage_metadata'):
        usage = response.usage_metadata
        
        # Get all available attributes
        print("\nRaw usage_metadata attributes:")
        for attr in dir(usage):
            if not attr.startswith('_'):
                try:
                    value = getattr(usage, attr)
                    if not callable(value):
                        print(f"  {attr}: {value}")
                except:
                    pass
        
        # Standard token counts
        input_tokens = getattr(usage, 'prompt_token_count', None)
        output_tokens = getattr(usage, 'candidates_token_count', None)
        total_tokens = getattr(usage, 'total_token_count', None)
        
        print("\n" + "-" * 40)
        print("EXTRACTED TOKEN COUNTS:")
        print("-" * 40)
        print(f"  Input Tokens:  {input_tokens:,}" if input_tokens else "  Input Tokens:  NOT AVAILABLE")
        print(f"  Output Tokens: {output_tokens:,}" if output_tokens else "  Output Tokens: NOT AVAILABLE")
        print(f"  Total Tokens:  {total_tokens:,}" if total_tokens else "  Total Tokens:  NOT AVAILABLE")
        
        # Validate and calculate thinking tokens
        print("\n" + "-" * 40)
        print("THINKING TOKENS ANALYSIS (Gemini 2.5 Feature):")
        print("-" * 40)
        
        if input_tokens and output_tokens and total_tokens:
            calculated_total = input_tokens + output_tokens
            thinking_tokens = total_tokens - calculated_total
            
            print(f"  Input Tokens:        {input_tokens:,}")
            print(f"  Output Tokens:       {output_tokens:,}")
            print(f"  Thinking Tokens:     {thinking_tokens:,}  ← HIDDEN from output but BILLED")
            print(f"  ---------------------------------")
            print(f"  Total Tokens:        {total_tokens:,}")
            
            if thinking_tokens > 0:
                thinking_pct = (thinking_tokens / total_tokens) * 100
                print(f"\n  ⚠ THINKING TOKENS: {thinking_pct:.1f}% of total usage!")
                print(f"  These are billed at OUTPUT token rates.")
                print(f"  Billable output = {output_tokens + thinking_tokens:,} tokens")
        
        # Estimate costs (Gemini 2.5 Flash-Lite pricing - Official)
        print("\n" + "-" * 40)
        print("COST ESTIMATION (Gemini 2.5 Flash-Lite):")
        print("-" * 40)
        input_rate = 0.10 / 1_000_000  # $0.10 per 1M input tokens
        output_rate = 0.40 / 1_000_000  # $0.40 per 1M output tokens (incl. thinking)
        
        if input_tokens and output_tokens:
            # Calculate with and without thinking tokens
            input_cost = input_tokens * input_rate
            output_cost_without_thinking = output_tokens * output_rate
            
            if thinking_tokens > 0:
                thinking_cost = thinking_tokens * output_rate  # Thinking billed as output
                output_cost_with_thinking = (output_tokens + thinking_tokens) * output_rate
                
                print(f"\n  WITHOUT thinking tokens (WRONG):")
                print(f"    Input Cost:  ${input_cost:.6f}")
                print(f"    Output Cost: ${output_cost_without_thinking:.6f}")
                print(f"    Total Cost:  ${input_cost + output_cost_without_thinking:.6f}")
                
                print(f"\n  WITH thinking tokens (CORRECT):")
                print(f"    Input Cost:    ${input_cost:.6f}")
                print(f"    Output Cost:   ${output_cost_with_thinking:.6f}")
                print(f"    Total Cost:    ${input_cost + output_cost_with_thinking:.6f}")
                
                cost_diff = (input_cost + output_cost_with_thinking) - (input_cost + output_cost_without_thinking)
                print(f"\n  💰 COST DIFFERENCE: ${cost_diff:.6f} ({(cost_diff/(input_cost + output_cost_without_thinking))*100:.1f}% more)")
            else:
                total_cost = input_cost + output_cost_without_thinking
                print(f"  Input Cost:  ${input_cost:.6f}")
                print(f"  Output Cost: ${output_cost_without_thinking:.6f}")
                print(f"  Total Cost:  ${total_cost:.6f}")
        
        return True
    else:
        print("\n❌ ERROR: usage_metadata NOT AVAILABLE in response!")
        print("This means token counting will NOT work.")
        return False


def test_with_system_prompt():
    """Test with system prompt to see if it affects token count."""

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return

    from google import genai
    from google.genai import types

    print("\n" + "=" * 60)
    print("TEST WITH SYSTEM PROMPT")
    print("=" * 60)

    client = genai.Client(api_key=api_key)

    system_prompt = """You are an expert document classifier.
    Classify each paragraph with the correct style tag.
    Output JSON array format."""

    generation_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
        system_instruction=system_prompt
    )

    user_prompt = """Classify:
[1] CHAPTER 1
[2] Test Title
Return JSON: [{"id": 1, "tag": "CN"}, {"id": 2, "tag": "CT"}]"""

    print(f"\nSystem Prompt: {len(system_prompt)} chars")
    print(f"User Prompt: {len(user_prompt)} chars")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=types.Content(
            role="user",
            parts=[types.Part(text=user_prompt)]
        ),
        config=generation_config
    )
    
    if hasattr(response, 'usage_metadata'):
        usage = response.usage_metadata
        input_tokens = getattr(usage, 'prompt_token_count', 0)
        output_tokens = getattr(usage, 'candidates_token_count', 0)
        total_tokens = getattr(usage, 'total_token_count', 0)
        thinking_tokens = max(0, total_tokens - input_tokens - output_tokens)
        
        print(f"\nResults:")
        print(f"  Input Tokens:    {input_tokens:,}")
        print(f"  Output Tokens:   {output_tokens:,}")
        print(f"  Thinking Tokens: {thinking_tokens:,}")
        print(f"  Total Tokens:    {total_tokens:,}")
        print("\n  Note: Input tokens include BOTH system prompt AND user prompt")
        print("  Note: Thinking tokens are billed as output tokens")


if __name__ == "__main__":
    print("\n🔍 Starting Token Verification...\n")
    
    success = test_token_counting()
    
    if success:
        test_with_system_prompt()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\n📝 SUMMARY:")
    print("   Gemini 2.5 models have 'thinking tokens' that are:")
    print("   - NOT shown in candidates_token_count (output)")
    print("   - INCLUDED in total_token_count")
    print("   - BILLED at output token rates")
    print("   - Can be 50-70% of total tokens!")
    print("\n   The classifier.py has been updated to account for this.")
    print("=" * 60)
