import csv
import json
import re

def count_leading_spaces(text):
    return len(text) - len(text.lstrip(' '))

def parse_hierarchy(filepath):
    # Mapping of 6-digit account core to a list of its parent categories
    account_mapping = {}
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        
        stack = [] # tuples of (level_spaces, name)
        
        for row in reader:
            if not row or not row[0]: continue
            
            raw_text = row[0]
            spaces = count_leading_spaces(raw_text)
            text = raw_text.strip()
            
            # Skip "Total xxx" lines
            if text.startswith("Total "):
                continue
                
            # Pop stack to maintaining correct hierarchy depth
            while stack and stack[-1][0] >= spaces:
                stack.pop()
                
            # Is this an account line? Starts with 6 digits
            match = re.match(r'^(\d{6})\s+(.*)', text)
            if match:
                core_acct = match.group(1)
                desc = match.group(2)
                
                # Build the hierarchy list from the stack
                hierarchy = [item[1] for item in stack]
                
                # We optionally strip out the Fund-level groupings if they are redundant, 
                # but let's just keep the full hierarchy for now.
                account_mapping[core_acct] = hierarchy
            else:
                # It's a category header
                if text not in ["Assets", "Liabilities & Net Assets", "Revenues", "Expenses", "Net Total"]:
                    stack.append((spaces, text))
                    
    return account_mapping

def main():
    bs_map = parse_hierarchy("References (delete later...)/Balance Sheet - All Funds (1).csv")
    re_map = parse_hierarchy("References (delete later...)/R & E - All Funds - Simplified.csv")
    
    # Merge mappings
    full_map = {**bs_map, **re_map}
    
    # Load existing coa_mapping.json
    with open('coa_mapping.json', 'r') as f:
        coa = json.load(f)
        
    # We will store this new multi-level mapping in a new key
    coa['multi_level_mapping'] = full_map
    
    with open('coa_mapping.json', 'w') as f:
        json.dump(coa, f, indent=4)
        
    print(f"Extracted {len(full_map)} account hierarchies.")

if __name__ == '__main__':
    main()
