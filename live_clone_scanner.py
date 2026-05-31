import os
import re
import math
import json
import time
import shutil
import urllib.request
import urllib.error
import subprocess
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# CONFIGURATION & ENV LOADING
# ==========================================
# Attempt to load Telegram environment variables from the local .env file
try:
    # Read the .env file placed in the same folder as this script
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    with open(env_path, 'r') as f:
        env_vars = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.startswith("#"))
        TELEGRAM_TOKEN = env_vars.get("TELEGRAM_TOKEN", "").strip()
        TELEGRAM_CHAT_ID = env_vars.get("TELEGRAM_CHAT_ID", "").strip()
        GITHUB_TOKEN = env_vars.get("GITHUB_TOKEN", os.getenv("GITHUB_TOKEN", "")).strip()
except Exception:
    TELEGRAM_TOKEN = ""
    TELEGRAM_CHAT_ID = ""
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# We configure 5 simultaneous clones to avoid local network/CPU overload
THREADS = 5
TEMP_DIR = "/tmp/git_clone_scanner"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ==========================================
# EXTENDED REGEX PATTERNS (AI + CREDS + DATABASES)
# ==========================================
PATTERNS = {
    "Anthropic API Key": r"sk-ant-api03-[A-Za-z0-9\-_]{80,95}",
    "OpenAI API Key": r"sk-[a-zA-Z0-9]{48}",
    "AWS Access Key": r"AKIA[0-9A-Z]{16}",
    "AWS Secret Key": r"(?i)aws_secret_access_key\s*=\s*[a-zA-Z0-9/+=]{40}",
    "GCP API Key": r"AIza[0-9A-Za-z\-_]{35}",
    "Slack Token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
    "GitHub Token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "MongoDB URI": r"mongodb(?:\+srv)?:\/\/[^\s]+",
    "Postgres URI": r"postgres(?:ql)?:\/\/[^\s]+",
    "Discord Webhook": r"https:\/\/discord\.com\/api\/webhooks\/[0-9]{17,19}\/[a-zA-Z0-9\-_]{68}",
    "Stripe Secret Key": r"sk_live_[0-9a-zA-Z]{24}",
    "RSA Private Key": r"-----BEGIN RSA PRIVATE KEY-----"
}

def send_telegram_alert(provider, repo_name, match_preview):
    """Sends a formatted alert directly to the user's Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return # Skip if Telegram isn't configured
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    message = (
        f"🚨 <b>CREDENTIAL LEAK DETECTED</b> 🚨\n\n"
        f"<b>Type:</b> {provider}\n"
        f"<b>Repository:</b> <a href='https://github.com/{repo_name}'>Click Here</a>\n"
        f"<b>Key Preview:</b> <code>{match_preview[:12]}...</code>\n\n"
        f"<i>Speed of Internet scanning from live tracker plugin</i>"
    )
    
    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode('utf-8')
    headers = {"Content-Type": "application/json"}
    
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def get_github_events():
    """Polls GitHub's global public events API for new pushes."""
    url = "https://api.github.com/events"
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "GlobalScanner"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching GitHub events (rate limit?): {e}")
        return []

def scan_file(filepath):
    """Reads a single file and scans against Regex patterns."""
    found_secrets = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        for provider, pattern in PATTERNS.items():
            matches = set(re.findall(pattern, content))
            for match in matches:
                found_secrets.append({"provider": provider, "match": match})
                
    except Exception:
        pass # Ignore binary files or permission errors
    return found_secrets

def clone_scan_and_destroy(repo_url, repo_name):
    """The core engine: 1. Clone, 2. Scan, 3. Obliterate."""
    # Create a unique temp folder for this run
    repo_hash = str(time.time()).replace('.', '')[-8:]
    clone_dir = os.path.join(TEMP_DIR, repo_hash)
    
    # 1. Clone (Shallow copy, ultra fast, no history)
    print(f"[*] Cloning: {repo_name}...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, clone_dir],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
        )
    except subprocess.TimeoutExpired:
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir, ignore_errors=True)
        return

    # If clone failed/was interrupted, bail
    if not os.path.exists(clone_dir):
        return

    # 2. Scan locally
    try:
        for root, dirs, files in os.walk(clone_dir):
            # Skip massive node_modules instantly
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', 'venv']]
            for file in files:
                filepath = os.path.join(root, file)
                # target specific extensions for speed
                if file.endswith(('.env', '.js', '.py', '.json', '.yml', '.yaml', '.txt', '.md', '.csv', '.rb', '.go')):
                    secrets = scan_file(filepath)
                    for secret in secrets:
                        print("\n" + "="*50)
                        print(f"🚨 ALERT! Found {secret['provider']} in {repo_name}!")
                        print(f"   Secret: {secret['match'][:12]}...")
                        print("="*50 + "\n")
                        
                        # Trigger Telegram Alert
                        send_telegram_alert(secret['provider'], repo_name, secret['match'])

    finally:
        # 3. Destroy EVERYTHING (Crucial to zero disk usage)
        shutil.rmtree(clone_dir, ignore_errors=True)
        print(f"    [-] Obliterated repo from local disk: {repo_name}")

def main():
    print("=" * 60)
    print("STARTING HIGH-SPEED GIT-CLONE SECRET RADAR")
    print(f"Temp Directory: {TEMP_DIR}")
    print(f"Threads: {THREADS}")
    if not TELEGRAM_CHAT_ID:
        print("WARNING: TELEGRAM_CHAT_ID is missing from .env. Alerts will only print to console!")
    print("=" * 60)

    last_event_id = None
    # We use ThreadPoolExecutor to literally download and scan 5 repos at the exact same time
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        while True:
            events = get_github_events()
            new_repos = []
            
            for event in events:
                if event['id'] == last_event_id:
                    break
                if event['type'] == 'PushEvent':
                    repo_name = event['repo']['name']
                    # construct raw GitHub URL
                    repo_url = f"https://github.com/{repo_name}.git"
                    if repo_url not in new_repos:
                        new_repos.append((repo_url, repo_name))
            
            if events:
                last_event_id = events[0]['id']
                
            # Submit off to the async workers
            for r_url, r_name in new_repos:
                executor.submit(clone_scan_and_destroy, r_url, r_name)
                
            # Wait briefly before pulling new live events
            time.sleep(10)

if __name__ == "__main__":
    main()
