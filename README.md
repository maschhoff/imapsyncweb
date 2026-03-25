# imapsync Web UI

A modern, dark-themed web interface for [imapsync](https://github.com/imapsync/imapsync) — 
the IMAP migration and backup tool.

## Features

- **Side-by-side server config** for source and destination IMAP accounts
- **Toggle switches** for SSL/TLS, dry run, delete, subscribe and more
- **Live log streaming** with color-coded output (transfers, errors, warnings, folders)
- **Real-time stats**: messages transferred, skipped, bytes, errors
- **Command preview** showing the exact imapsync command that will run
- **Job history** with status tracking
- **Stop running jobs** with a click

![Screenshot](https://raw.githubusercontent.com/maschhoff/imapsyncweb/refs/heads/main/Screenshot.png)

## Requirements

- Python 3.8+
- Flask
- `imapsync` installed on the system

## Install imapsync

**Docker**
```bash
docker run -d \
  --name='imapsyncweb' \
  --network bridge \
  -p 5000:5000 \
  knex666/imapsyncweb
```

**Debian/Ubuntu:**
```bash
apt-get install imapsync
```

**macOS (Homebrew):**
```bash
brew install imapsync
```

**From source:**
```bash
git clone https://github.com/imapsync/imapsync
cd imapsync
# Follow INSTALL instructions
```

## Run the Web UI

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.

## Usage

1. Fill in **Source Server** (the account you want to migrate FROM)
2. Fill in **Destination Server** (the account you want to migrate TO)
3. Configure options (enable **Dry Run** first to test without copying)
4. Click **Start Migration**
5. Switch to the **Jobs** tab to watch live output

## Security Note

This app runs locally. Do not expose it to the internet — it handles 
email credentials which should never be exposed publicly.
