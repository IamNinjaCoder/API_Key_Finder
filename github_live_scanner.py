import urllib.request
import urllib.error
import json
import re
import time
import os

# Your Personal Access Token (PAT) is highly recommended. 
# GitHub unauthenticated API limit is 60 requests per hour, which you will hit in seconds.
# Set it in your terminal before running: export GITHUB_TOKEN="ghp_your_token_here"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Regex Patterns for API Keys
PATTERNS = {
    "Anthropic": r"sk-ant-api03-[A-Za-z0-9\-_]{80,95}",
    "OpenAI": r"sk-[a-zA-Z0-9]{48}",
    "AWS Access Key": r"AKIA[0-9A-Z]{16}",
    "Slack Token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
    "GitHub Token": r"gh[pousr]_[A-Za-z0-9]{36}"
}

def get_headers():
    headers = {
        "Accept": "application/vnd.github.v3+json", 
        "User-Agent": "GlobalSecretScannerBot"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def fetch_json(url):
    """Hits the GitHub API and returns the parsed JSON."""
    req = urllib.request.Request(url, headers=get_headers())
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 403 or e.code == 429:
            print("\n[!] GitHub API Rate Limit Exceeded!")
            print("    Please set a GITHUB_TOKEN environment variable to increase your limit.")
            time.sleep(30) # Wait so we don't crash or get completely IP banned
        return None
    except Exception as e:
        return None

def scan_commit(repo_name, commit_sha, html_url):
    """Downloads the diff/patch for a specific commit and checks it for Regex matches."""
    api_url = f"https://api.github.com/repos/{repo_name}/commits/{commit_sha}"
    commit_data = fetch_json(api_url)
    
    # If commit data exists and contains files
    if not commit_data or 'files' not in commit_data: 
        return

    for file in commit_data['files']:
        # 'patch' contains the raw text changes in the commit
        patch = file.get('patch', '')
        if not patch:
            continue
        
        # Scan the code diff for secrets
        for provider, pattern in PATTERNS.items():
            matches = set(re.findall(pattern, patch))
            for match in matches:
                print("\n" + "!" * 60)
                print(f"🚨 LIVE LEAK DETECTED: {provider} Key 🚨")
                print(f"Repository: https://github.com/{repo_name}")
                print(f"Commit URL: {html_url}")
                print(f"Key Preview: {match[:8]}...{match[-4:]}")
                print("!" * 60 + "\n")

def monitor_live_events():
    """Listens to the GitHub global /events stream for PushEvents."""
    print("=" * 60)
    print("Starting Live Global Secret Scanner...")
    print("Listening to real-time GitHub pushes globally. (Press Ctrl+C to stop)")
    print("=" * 60)
    
    if not GITHUB_TOKEN:
        print("WARNING: Running without GITHUB_TOKEN.")
        print("You are restricted to 60 API requests per hour and will be ratelimited quickly.\n")
    
    last_event_id = None
    
    while True:
        # Fetch the 30 most recent public events on GitHub across the entire planet
        events = fetch_json("https://api.github.com/events")
        if not events:
            time.sleep(10)
            continue
            
        for event in events:
            # Stop if we hit the event we already processed in the last polling loop
            if event['id'] == last_event_id:
                break
                
            # We only care about people pushing code (PushEvent)
            if event['type'] == 'PushEvent':
                repo_name = event['repo']['name']
                commits = event['payload'].get('commits', [])
                
                for commit in commits:
                    sha = commit['sha']
                    html_url = f"https://github.com/{repo_name}/commit/{sha}"
                    print(f"Scanning push to: {repo_name}...")
                    
                    # Offload the commit scanning
                    scan_commit(repo_name, sha, html_url)
                    
        if events:
            last_event_id = events[0]['id']
            
        # Wait 10 seconds before asking GitHub for new events to avoid getting banned
        time.sleep(10)

if __name__ == "__main__":
    monitor_live_events()
