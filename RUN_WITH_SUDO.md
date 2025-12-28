# Running with Sudo for Full Network Scanning

## Why Sudo is Needed

The network scanner now uses **Scapy** for pure Python ARP scanning (no subprocess calls). This provides:

- ✅ Pure Python implementation (no subprocess)
- ✅ Active network scanning
- ✅ Finds all devices on the network
- ✅ More reliable than reading ARP cache

However, Scapy requires **elevated permissions** to access raw sockets (BPF devices on macOS, raw sockets on Linux).

## Running the Backend with Sudo

### Option 1: Quick Start Script (Recommended)

```bash
cd backend
./start-with-sudo.sh
```

This script will:
1. Activate the virtual environment
2. Prompt for your password
3. Run the backend with sudo

### Option 2: Manual Command

```bash
cd backend
source .venv/bin/activate
sudo .venv/bin/python main.py
```

**Important:** Use `.venv/bin/python` (not just `python`) to ensure you're using the virtual environment's Python with all dependencies installed.

### Option 3: Run Without Sudo (Limited)

You can run without sudo, but it will only show your local machine:

```bash
cd backend
source .venv/bin/activate
python main.py
```

The backend will display a warning and only discover the local device.

## Full Stack Startup with Sudo

If you want to start both frontend and backend together:

### Terminal 1 - Backend with sudo:
```bash
cd backend
./start-with-sudo.sh
```

### Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

## Security Considerations

Running a web service with sudo is generally not recommended for production. This is a **local development tool** only.

For production deployments, consider:

1. **Setting BPF device permissions** (macOS):
   ```bash
   sudo chmod 666 /dev/bpf*
   ```
   Note: This needs to be done after each reboot

2. **Using capabilities** (Linux):
   ```bash
   sudo setcap cap_net_raw=eip /path/to/python
   ```

3. **Running in a container** with appropriate network privileges

4. **Using a dedicated scanning service** that runs with elevated permissions and communicates via IPC

## Troubleshooting

### "sudo: a terminal is required to read the password"

This happens when running in a non-interactive environment. Solution:
- Run the command from a terminal, not from a script without TTY
- Use the provided `start-with-sudo.sh` script

### "Permission denied: could not open /dev/bpf0"

This means:
- You're not running with sudo
- Run with: `sudo .venv/bin/python main.py`

### "No devices found" even with sudo

1. Make sure other devices are on your network
2. Try pinging another device first: `ping <device-ip>`
3. Check your firewall settings
4. Verify your network interface is active: `ifconfig` or `ip addr`

## How It Works

The scanner uses this strategy:

1. **Try Scapy active scanning** (requires sudo)
   - Sends ARP broadcast to all IPs in subnet
   - Collects responses
   - Most comprehensive method

2. **Fallback to ARP cache file** (Linux only, no sudo needed)
   - Reads `/proc/net/arp` directly
   - Only shows devices that have communicated recently

3. **Always shows local machine**
   - No scanning needed for localhost

## Example Output

With sudo:
```
Found 16 devices:
  192.168.1.1     ac:91:9b:6b:c7:e1    Unknown
  192.168.1.156   dc:a6:32:de:4b:e4    Unknown
  192.168.1.158   98:6e:e8:2f:99:42    Unknown
  ...
```

Without sudo:
```
Found 1 device:
  192.168.1.173   local                Bobs-Mac-mini.local (This Device)
```
