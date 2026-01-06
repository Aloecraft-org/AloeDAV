import re
from typing import List, Dict, Union, Tuple

def unfold_lines(text: str) -> List[str]:
    """
    Unfolds lines according to RFC 5545 (iCalendar) / RFC 6350 (vCard).
    Removes the CRLF (or LF) followed by a space or tab used for folding.
    """
    # 1. Normalize line endings to avoid regex complexity with mixed CRLF/LF
    text = text.replace('\r\n', '\n')
    
    # 2. Unfold: specific regex for "newline followed by space or tab"
    #    The captured group is replaced by nothing, effectively joining the lines.
    unfolded = re.sub(r'\n[ \t]', '', text)
    
    # 3. Split back into a list of lines, filtering empty ones
    return [line for line in unfolded.split('\n') if line.strip()]

def parse_content_lines(lines: List[str]) -> Dict[str, Union[str, Tuple[Dict[str, str], str]]]:
    """
    Parses unfolded lines into a dictionary.
    
    Format: KEY;PARAM1=VAL1;PARAM2=VAL2:Value
    
    Returns:
        {
            'KEY': 'Value',
            'KEY_WITH_PARAMS': ({'PARAM1': 'VAL1'}, 'Value')
        }
    """
    result = {}
    
    for line in lines:
        if ':' not in line:
            continue
            
        # 1. Split into KeyPart and ValuePart at the first colon
        key_part, value = line.split(':', 1)
        
        # 2. Check for parameters (semicolon in key_part)
        if ';' in key_part:
            # Split Key and Params
            parts = key_part.split(';')
            key_name = parts[0]
            params_raw = parts[1:]
            
            params = {}
            for p in params_raw:
                if '=' in p:
                    p_key, p_val = p.split('=', 1)
                    params[p_key] = p_val
                else:
                    # Handle valueless params or type flags if necessary
                    params[p] = True
            
            result[key_name] = (params, value)
        else:
            result[key_part] = value
            
    return result

if __name__ == "__main__":
    import sys
    import os
    
    # Verify imports work by adding src to path if running directly
    # sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    
    try:
        from aloedav import testdata
    except ImportError:
        # Fallback for direct execution if package structure isn't set up in env
        print("Warning: Could not import testdata from package. Ensure PYTHONPATH is set.")
        # Mock data for standalone test if import fails
        class MockData:
            TEST_VCARD_FOLDED = """BEGIN:VCARD
NOTE:This is a long note that is folded over multiple lines to test the unfo
 lding logic of the utility function.
END:VCARD"""
        testdata = MockData()

    print("--- Testing Unfold Logic ---")
    
    # 1. Test Folding
    print(f"Original Folded Input:\n{testdata.TEST_VCARD_FOLDED}\n")
    unfolded_lines = unfold_lines(testdata.TEST_VCARD_FOLDED)
    
    print("Unfolded Lines:")
    for i, line in enumerate(unfolded_lines):
        print(f"{i+1}: {line}")

    # Check specific folded content
    note_line = next((l for l in unfolded_lines if l.startswith("NOTE:")), "")
    if "test the unfolding logic" in note_line and "unfo lding" not in note_line:
        print("\n[PASS] 'NOTE' line unfolded correctly (newlines removed).")
    else:
        print("\n[FAIL] 'NOTE' line did not unfold as expected.")

    print("\n--- Testing Parse Logic ---")
    parsed = parse_content_lines(unfolded_lines)
    
    # Check simple field
    if parsed.get('VERSION') == '3.0':
        print("[PASS] VERSION parsed correctly.")
    
    # Check parameterized field (ADR in vCard)
    adr = parsed.get('ADR')
    if adr and isinstance(adr, tuple):
        params, val = adr
        if params.get('TYPE') == 'WORK' and 'United States' in val:
             print("[PASS] ADR (Address) parsed with parameters correctly.")
        else:
            print(f"[FAIL] ADR parsing mismatch: {adr}")
    elif 'ADR' in str(testdata.TEST_VCARD_FOLDED): # Only fail if ADR was actually in input
         print(f"[FAIL] ADR not found or not tuple: {adr}")

# Outputs:

# > --- Testing Unfold Logic ---
# > Original Folded Input:
# > BEGIN:VCARD
# > VERSION:3.0
# > FN:Folded Line Tester
# > N:Tester;Folded;;;
# > NOTE:This is a long note that is folded over multiple lines to test the unfo
# >  lding logic of the utility function. It should appear as a single continuous
# >   line after processing.
# > ADR;TYPE=WORK:;;100 Waters Edge;Baytown;LA;30314;United States of Amer
# >  ica
# > END:VCARD
# > 
# > Unfolded Lines:
# > 1: BEGIN:VCARD
# > 2: VERSION:3.0
# > 3: FN:Folded Line Tester
# > 4: N:Tester;Folded;;;
# > 5: NOTE:This is a long note that is folded over multiple lines to test the unfolding logic of the utility function. It should appear as a single continuous line after processing.
# > 6: ADR;TYPE=WORK:;;100 Waters Edge;Baytown;LA;30314;United States of America
# > 7: END:VCARD
# > 
# > [PASS] 'NOTE' line unfolded correctly (newlines removed).
# > 
# > --- Testing Parse Logic ---
# > [PASS] VERSION parsed correctly.
# > [PASS] ADR (Address) parsed with parameters correctly.