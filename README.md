# API Key Finder (Zero-Cost OSINT Radar)

A highly optimized, multi-threaded GitHub secret scanning radar. This tool actively monitors global GitHub push events via the public events API. It performs lightning-fast shallow clones directly to a temporary directory, scans for a massive list of cloud credentials and AI API keys using regex and entropy engines, and immediately obliterates the clone from the disk to preserve storage.

Features:
- **Zero Cost & Disk Efficient:** Uses standard `/tmp/` and recursive destruction to ensure the host machine never runs out of space.
- **High-Speed Concurrency:** Utilizes ThreadPoolExecutors to scan multiple repos identically.
- **Telegram Alerting:** Instant push notifications forwarded to a Telegram bot.
- **Dependency Free:** Requires ZERO `pip install` commands. Everything runs off Python3 standard libraries.

## Deployment (AWS EC2 / VPS)
1. Clone this repository on your VPS.
2. Run `cp .env.example .env` and fill in your details.
3. Use a tool like `tmux` or `nohup` to run the file endlessly in the background:
```bash
nohup python3 live_clone_scanner.py &
```
