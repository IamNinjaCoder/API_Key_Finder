import os
import re
import math
import json
import urllib.request
import urllib.error

# 1. Regex Patterns for Provider Specific Keys
PATTERNS = {
    "Anthropic": r"sk-ant-api03-[A-Za-z0-9\-_]{80,95}",
    "OpenAI": r"sk-[a-zA-Z0-9]{48}",
    "AWS Access Key": r"AKIA[0-9A-Z]{16}",
    "Slack Token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
    "GitHub Token": r"gh[pousr]_[A-Za-z0-9]{36}"
}

def calculate_entropy(data_string):
    """Calculate the Shannon entropy of a string (measures randomness)."""
    if not data_string:
        return 0
    entropy = 0
    for x in set(data_string):
        p_x = float(data_string.count(x)) / len(data_string)
        entropy += - p_x * math.log(p_x, 2)
    return entropy

def check_anthropic_key_live(api_key):
    """Tests if an Anthropic key is highly active and valid."""
    print(f"    [+] Performing live validation on Anthropic key...")
    url = "https://api.anthropic.com/v1/messages"
    data = json.dumps({
        "model": "claude-3-haiku-20240307",
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "ping"}]
    }).encode('utf-8')
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return "ACTIVE! 🚨 (This key is live and dangerous)"
            return f"UNKNOWN STATE (HTTP {response.status})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "REVOKED or INVALID ✅"
        return f"HTTP Error: {e.code}"
    except Exception as e:
        return f"Error connecting to validation server: {e}"

def scan_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        found_something = False

        # 1. Check Regex patterns
        for provider, pattern in PATTERNS.items():
            matches = set(re.findall(pattern, content))
            for match in matches:
                if not found_something: 
                    print(f"\nScanning: {filepath}")
                    found_something = True
                # Redact the middle of the key for safety during output
                print(f"  [!] Found {provider} Key: {match[:8]}...{match[-4:]}")
                
                # 2. Live Validation for Anthropic 
                if provider == "Anthropic":
                    status = check_anthropic_key_live(match)
                    print(f"      Status: {status}")
                
        # 3. Simple entropy check to find generic long random strings
        # Finds strings between 30 and 100 chars with high randomness score
        words = re.split(r'\s+|=|"|\'', content)
        for word in words:
            if 30 < len(word) < 100:
                ent = calculate_entropy(word)
                # An entropy score over >4.5 identifies mathematically random strings (like Base64 padding)
                if ent > 4.5 and not any(re.match(p, word) for p in PATTERNS.values()):
                    if not found_something: 
                        print(f"\nScanning: {filepath}")
                        found_something = True
                    print(f"  [?] High Entropy String (Potential Secret): {word[:8]}... (Entropy: {ent:.2f})")

    except Exception as e:
        pass # Ignore unreadable files

def run_scanner(directory="."):
    print(f"Starting Custom Secret Scanner on directory: {directory}")
    print("=" * 60)
    for root, dirs, files in os.walk(directory):
        # Skip scanning git histories and virtual environments
        dirs[:] = [d for d in dirs if d not in ['.git', 'venv', 'env', '__pycache__', 'node_modules']]
        for file in files:
            filepath = os.path.join(root, file)
            # Basic filter to target source code and config files only
            if file.endswith(('.py', '.txt', '.md', '.json', '.env', '.csv', '.yml', '.js')):
                scan_file(filepath)
    print("=" * 60)
    print("Scan Complete!")

if __name__ == "__main__":
    # Scans the directory you run the script from by default
    run_scanner(".")
