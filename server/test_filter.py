import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from server.core.word_filter import WordFilter

def test_word_filter():
    wf = WordFilter("blocked_words.txt")
    
    # Test cases
    test_cases = [
        ("Merhaba dünya", False),
        ("Nasılsın?", False),
        ("Sen gerizekalı mısın?", True),
        ("Aptal herif", True),
        ("Bu bir alan adıdır", False), # False positive check (lan in alan)
        ("Pipi ve kaka", True),
    ]
    
    print("\n--- Testing contains_profanity ---")
    all_passed = True
    for text, expected in test_cases:
        result = wf.contains_profanity(text)
        status = "PASSED" if result == expected else "FAILED"
        print(f"Text: '{text}' | Expected: {expected} | Result: {result} | {status}")
        if result != expected:
            all_passed = False
            
    print("\n--- Testing censor_text ---")
    censor_cases = [
        ("Selam aptal", "Selam ***"),
        ("Kaka yapma", "*** yapma"),
        ("Normal bir cümle", "Normal bir cümle"),
    ]
    
    for text, expected in censor_cases:
        result = wf.censor_text(text)
        status = "PASSED" if result == expected else "FAILED"
        print(f"Text: '{text}' | Expected: '{expected}' | Result: '{result}' | {status}")
        if result != expected:
            all_passed = False
            
    if all_passed:
        print("\n✅ ALL TESTS PASSED")
    else:
        print("\n❌ SOME TESTS FAILED")

if __name__ == "__main__":
    test_word_filter()
