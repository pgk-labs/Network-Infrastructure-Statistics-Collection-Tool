# Network-Infrastructure-Statistics-Collection-Tool
A robust, multi-threaded Python tool for collecting statistics from network infrastructure devices (Cisco, HPE, FortiGate) using pyATS/Genie framework.

🚀 Features

Multi-vendor Support: Cisco (IOS, NX-OS, IOS-XE), HPE, and FortiGate devices
Parallel Execution: Concurrent device connections and command execution for improved performance
Flexible Scheduling: Interval-based command execution with persistent state management
TextFSM Parsing Support: Structured data extraction from CLI outputs
Comprehensive Error Handling: Robust error recovery and detailed logging
Email Notifications: Automated reporting of execution results and failures
Thread-Safe Operations: Safe concurrent operations with proper synchronization
Configurable Timeouts: Device and command-specific timeout settings

📋 Table of Contents

Installation
Dependencies
Configuration
Usage
File Structure
License

🛠️ Installation
Prerequisites

Python 3.7+
Access to network devices via SSH/Telnet
Valid device credentials

Clone Repository
git clone https://github.com/pgk-labs/Network-Infrastructure-Statistics-Tool.git
cd Network-Infrastructure-Statistics-Tool
Install Dependencies
pip install -r requirements.txt

Setup Configuration Files

Create your testbed configuration
Define device commands and schedules
Configure email settings

🚀 Usage
on cli run pyats run job infrastructure_job.py

Scheduling with Cron
Add to your crontab for automated execution:
# Run every hour
0 * * * * cd /path/to/Network-Infrastructure-Statistics-Tool && /usr/bin/python3 -m pyats run job network-infrastructure_job.py

# Run every 15 minutes
*/15 * * * * cd /path/to/Network-Infrastructure-Statistics-Tool && /usr/bin/python3 -m pyats run job network-infrastructure_job.py

📁 File Structure
network-infrastructure-statistics/
├── README.md
├── requirements.txt
├── network-infrastructure-statistics_testscript.py          # Main script
├── network-infrastructure-statistics_testscript_no_threads.py          # Main script but no thread implementation
├── network-infrastructure-statistics_job.py        # pyATS job file
├── email_sender.py             # Email notification module
├── testbed.yaml               # Device definitions
├── commands.yaml              # Commands and schedules
├── last_run_times.json        # Execution state (auto-generated)
├── parsers/                   # TextFSM templates
│   ├── add your own parsers here
├── results/                   # Output directory (auto-generated)
│   └── YYYYMMDD_HHMMSS/      # Timestamped results
│       ├── device1/
│       │   ├── success/       # Successful command outputs
│       │   └── fail/          # Failed command outputs
│       └── device2/

📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

