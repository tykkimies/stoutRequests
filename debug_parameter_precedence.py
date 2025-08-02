#!/usr/bin/env python3

"""
Debug script to test parameter precedence logic in discover_category_more.
"""

def test_parameter_precedence():
    """Test the actual parameter precedence logic used in discover_category_more."""
    
    print("🔍 TESTING PARAMETER PRECEDENCE LOGIC")
    print("=" * 50)
    
    test_cases = [
        {
            "name": "Both parameters provided",
            "type": "movie",
            "media_type": "mixed"
        },
        {
            "name": "Only type provided (media_type is empty string)",
            "type": "mixed",
            "media_type": ""
        },
        {
            "name": "Only media_type provided (type is default)",
            "type": "movie",  # default value
            "media_type": "mixed"
        },
        {
            "name": "Neither provided (defaults)",
            "type": "movie",  # default value
            "media_type": ""   # default value
        },
        {
            "name": "User's scenario - URL query params",
            "type": "mixed",
            "media_type": "mixed"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n🧪 TEST CASE {i}: {case['name']}")
        print("-" * 30)
        
        type_param = case["type"]
        media_type_param = case["media_type"]
        
        # This is the exact logic from discover_category_more
        actual_media_type = media_type_param if media_type_param else type_param
        
        print(f"📥 Input:")
        print(f"  - type: '{type_param}'")
        print(f"  - media_type: '{media_type_param}'")
        print(f"  - media_type is truthy: {bool(media_type_param)}")
        print(f"  - media_type is empty string: {media_type_param == ''}")
        
        print(f"🔄 Logic:")
        print(f"  - actual_media_type = media_type if media_type else type")
        print(f"  - actual_media_type = '{media_type_param}' if '{media_type_param}' else '{type_param}'")
        print(f"  - actual_media_type = '{actual_media_type}'")
        
        print(f"📊 Result:")
        print(f"  - Will use media_type: '{actual_media_type}'")
        print(f"  - Is mixed: {actual_media_type == 'mixed'}")
        
        if actual_media_type != "mixed" and (type_param == "mixed" or media_type_param == "mixed"):
            print(f"  ❌ POTENTIAL BUG: Expected mixed but got '{actual_media_type}'")
        elif actual_media_type == "mixed":
            print(f"  ✅ Correct: Will use mixed content")

if __name__ == "__main__":
    test_parameter_precedence()