# ===============================
# Standard Python Libraries
# ===============================
import json
import os
from datetime import datetime
import yaml
import logging
import textfsm
import time

# ===============================
# pyATS / Genie Libraries
# ===============================
from pyats.aetest import Testcase, test, setup, cleanup
from genie.testbed import load

# ===============================
# Email Library
# ===============================
from email_sender import send_email


class infra_statistics(Testcase):
    """
    AEtest Testcase to:
    - Load device and command definitions
    - Identify which devices/commands are due for execution
    - Connect to devices sequentially
    - Run and parse commands
    - Save results and handle failures
    - Send a summary email report
    """

    # ---------------------------------------------------
    # Setup Section: Initialize testbed, devices, logging
    # ---------------------------------------------------
    @setup
    def load_files(self):
        # Initialize tracking variables
        self.connected_devices = {}           # Dict to store connected device objects
        self.fails = []                       # Stores failures across the run
        self.hpe_devices = []                 # HPE device list
        self.fortigate_devices = []  # FortiGate device list
        self.cisco_devices = {"ios": [], "nxos": [], "xe": []}  # Cisco devices by OS type
        self.create_time = datetime.now().strftime('%Y%m%d_%H%M%S')  # Timestamp for results
        self.logger = logging.getLogger(__name__)  # Logger for debug/info
        self.logger.setLevel(logging.INFO)

        # -------------------------
        # Load testbed.yaml
        # -------------------------
        try:
            self.testbed = load('testbed.yaml')
        except Exception as e:
            self.fails.append({'result': 'FAIL', 'error': str(e)})
            self.failed("Testbed file could not be loaded.")            

        # -------------------------
        # Load commands.yaml
        # -------------------------
        try:
            with open("commands.yaml", "r") as f:
                self.device_data = yaml.safe_load(f)

            # Parse HPE section
            for entry in self.device_data.get("hpe", []):
                self.hpe_devices.extend(entry.get("devices", []))

            # Parse Forti section
            for entry in self.device_data.get("forti", []):
                self.fortigate_devices.extend(entry.get("devices", []))

            # Parse Cisco section
            for entry in self.device_data.get("cisco", []):
                device_type = entry.get("type")
                if device_type in ["ios", "nxos", "xe"]:
                    self.cisco_devices[device_type].extend(entry.get("devices", []))
                else:
                    self.logger.warning(f"Unknown Cisco type '{device_type}' in YAML, skipping.")
            
            # Merge all device groups into allowed_devices set
            self.allowed_devices = set(
                self.cisco_devices["ios"] + 
                self.cisco_devices["nxos"] + 
                self.cisco_devices["xe"] + 
                self.hpe_devices + 
                self.fortigate_devices
            )
            self.passed("Yaml file loaded successfully.")
        except Exception as e:
            self.fails.append({'result': 'FAIL', 'error': str(e)})
            self.failed("Yaml file could not be loaded.")

    # ---------------------------------------------------
    # Test: Identify devices due for execution
    # ---------------------------------------------------
    @test
    def devices_due_for_run(self, steps):
        """
        Determine which devices have commands due for execution,
        based on intervals saved in last_run_times.json.
        """
        last_run_file = "last_run_times.json"
        # Load last execution times
        if os.path.exists(last_run_file):
            with open(last_run_file) as f:
                last_run_times = json.load(f)
        else:
            last_run_times = {}

        now = time.time()
        self.devices_to_run = []  # Devices that need commands executed

        # Loop through all allowed devices
        for device_name in self.allowed_devices:
            commands = infra_statistics.get_device_commands(self, device_name)
            device_last_run = last_run_times.get(device_name, {})
            due_commands = []

            # Check each command interval
            for cmd in commands:
                interval = cmd.get("interval", 0)
                last_run = device_last_run.get(cmd['command'], 0)
                if now - last_run >= interval:
                    due_commands.append(cmd['command'])

            # Record results
            if due_commands:
                self.devices_to_run.append(device_name)
                with steps.start(f"{device_name} has {len(due_commands)} command(s) to be executed") as step:
                    step.passed(f"Commands to be executed: {', '.join(due_commands)}")
            else:
                with steps.start(f"{device_name} has no commands to be executed") as step:
                    step.passed("No commands to execute")

        self.logger.info(f"Devices scheduled to run: {self.devices_to_run}")

    # ---------------------------------------------------
    # Test: Connect to devices sequentially
    # ---------------------------------------------------
    @test
    def establish_connections(self, steps):
        if not self.devices_to_run:
            self.logger.info("No devices have commands to be executed. Skipping connection step.")
            return
        
        self.forti_prompt = r'\(global\)\s?\$'  # Forti device prompt

        # Connect to each device sequentially
        for name in self.devices_to_run:
            with steps.start(f"Connecting to {name}") as step:
                if name not in self.allowed_devices:
                    error_msg = f"{name} is in testbed but not defined in YAML commands file."
                    self.logger.warning(f"Skipping {name}: not defined in YAML")
                    self.fails.append({
                        'device': name,
                        'result': 'FAIL',
                        'error': error_msg
                    })
                    step.passx(error_msg)
                    continue

                try:
                    device = self.testbed.devices[name]
                    
                    # Cisco devices
                    if name in self.cisco_devices["ios"] + self.cisco_devices["nxos"] + self.cisco_devices["xe"]:
                        device.connect(init_config_commands=[], init_exec_commands=[], log_stdout=False)
                        device.execute("terminal length 0")

                    # HPE devices
                    elif name in self.hpe_devices:
                        device.connect(log_stdout=False, learn_hostname=True,
                                    init_exec_commands=[], init_config_commands=[])
                        device.execute('screen-length disable')
                        device.execute('system-view')
                        device.execute("display version")

                    # Forti devices
                    elif name in self.fortigate_devices:
                        device.connect(init_exec_commands=[], init_config_commands=[],
                                    log_stdout=False, state_machine_class=None)
                        device.sendline("config global")
                        device.expect(self.forti_prompt, timeout=5)
                        device.sendline('show system interface')
                        device.expect(self.forti_prompt, timeout=5)

                    self.connected_devices[name] = device
                    step.passed(f"{name} connected successfully")

                except Exception as e:
                    error_msg = str(e)
                    self.fails.append({
                        'device': name,
                        'result': 'FAIL',
                        'error': error_msg
                    })
                    step.passx(f"{name} connection failed: {error_msg}")
   
    # ---------------------------------------------------
    # Static Method: Parse CLI output using TextFSM
    # ---------------------------------------------------
    @staticmethod
    def textfsm_parsers(self, command, raw_output, device_os, device_name):
        """
        Parse raw CLI output using TextFSM templates defined in YAML.
        Returns structured data (list of dicts) or raw output if no parser.
        """
        # Select correct YAML section
        if device_os in ["ios", "nxos"]:
            entries = self.device_data.get("cisco", {}).get(device_os, [])
        else:
            entries = self.device_data.get(device_os, [])

        # Match device and command
        for entry in entries:
            if device_name in entry.get("devices", []):
                for cmd in entry.get("commands", []):
                    if cmd.get("command") == command:
                        parser_path = cmd.get("textfsm")
                        if not parser_path:
                            return raw_output  # No parser defined
                        with open(parser_path) as f:
                            fsm = textfsm.TextFSM(f)
                            parsed_output = fsm.ParseText(raw_output)
                            return [dict(zip(fsm.header, row)) for row in parsed_output]

        # Fallback: return raw output
        return raw_output

    # ---------------------------------------------------
    # Static Method: Get all commands for a device
    # ---------------------------------------------------
    @staticmethod
    def get_device_commands(self, device_name):
        """
        Return a list of command dictionaries for the given device.
        Each dict includes 'command' and optional 'textfsm' keys.
        """
        commands_list = []

        for os_type, entries in self.device_data.items():
            if os_type == "cisco":
                # Cisco entries contain type and device lists
                for entry in entries:
                    if entry.get("type") in ["ios", "nxos", "xe"] and device_name in entry.get("devices", []):
                        for cmd_entry in entry.get("commands", []):
                            if isinstance(cmd_entry, dict) and 'command' in cmd_entry:
                                commands_list.append(cmd_entry)
                            elif isinstance(cmd_entry, str):
                                commands_list.append({'command': cmd_entry, 'textfsm': None})
                        return commands_list
            else:
                # Non-Cisco entries
                for entry in entries:
                    if device_name in entry.get("devices", []):
                        for cmd_entry in entry.get("commands", []):
                            if isinstance(cmd_entry, dict) and 'command' in cmd_entry:
                                commands_list.append(cmd_entry)
                            elif isinstance(cmd_entry, str):
                                commands_list.append({'command': cmd_entry, 'textfsm': None})
                        return commands_list

        return []  # No commands found

    # ---------------------------------------------------
    # Test: Execute commands sequentially
    # ---------------------------------------------------
    @test
    def collect_commands(self, steps):
        """
        Execute commands sequentially on each device.
        """
        if not self.connected_devices:
            self.logger.info("No devices connected. Skipping command collection.")
            return

        last_run_file = "last_run_times.json"
        if os.path.exists(last_run_file):
            with open(last_run_file) as f:
                last_run_times = json.load(f)
        else:
            last_run_times = {}

        now = time.time()

        # Process each device sequentially
        for device_name, device in self.connected_devices.items():
            # Identify device model
            if device_name in self.hpe_devices:
                model = "hpe"
            elif device_name in self.fortigate_devices:
                model = "forti"  
            else:
                model = "cisco"

            device_last_run = last_run_times.get(device_name, {})

            try:
                commands = infra_statistics.get_device_commands(self, device_name)
                filtered_commands = []

                # Filter by interval
                for cmd in commands:
                    interval = cmd.get("interval", 0)
                    last_run = device_last_run.get(cmd['command'], 0)
                    if now - last_run >= interval:
                        filtered_commands.append(cmd)

                if filtered_commands:
                    os.makedirs(f"results/{self.create_time}/{device_name}", exist_ok=True)

                    # Execute each command sequentially
                    for cmd in filtered_commands:
                        cmd_name = cmd['command']
                        safe_cmd = cmd_name.replace(" ", "_").replace("/", "_")
                        
                        with steps.start(f"Processing {cmd_name} on {device_name}") as step:
                            try:
                                # Execute command with device-specific timeout and settings
                                if model == "forti":
                                    raw_output = device.execute(cmd_name, timeout=10)
                                else:
                                    raw_output = device.execute(cmd_name)
                                    
                                # Parse output
                                try:
                                    parsed_output = infra_statistics.textfsm_parsers(
                                        self, cmd_name, raw_output, model, device_name
                                    )
                                except FileNotFoundError as e:
                                    parsed_output = raw_output
                                    # Save success with parsing error note
                                    os.makedirs(f"results/{self.create_time}/{device_name}/success", exist_ok=True)
                                    file_path = f"results/{self.create_time}/{device_name}/success/{device_name}_{safe_cmd}_no_parser.txt"
                                    with open(file_path, "w") as f:
                                        f.write(parsed_output)
                                    
                                    self.logger.warning(f"TextFSM parser not found for {cmd_name} on {device_name}: {str(e)}")
                                    step.passed(f"Success (no parser) - Output saved to {file_path}")
                                    device_last_run[cmd_name] = now
                                    continue
                                    
                                except Exception as e:
                                    # Save failure
                                    os.makedirs(f"results/{self.create_time}/{device_name}/fail", exist_ok=True)
                                    file_path = f"results/{self.create_time}/{device_name}/fail/{device_name}_{safe_cmd}_parsing_failed.json"
                                    with open(file_path, "w") as f:
                                        json.dump({"error": str(e), "raw_output": raw_output}, f, indent=4)
                                    
                                    self.fails.append({
                                        'device': device_name,
                                        'command': cmd_name,
                                        'result': 'FAIL',
                                        'error': f"Parsing error: {str(e)}"
                                    })
                                    
                                    print(f"\n{'='*60}")
                                    print(f"PARSING FAILED: {cmd_name}")
                                    print(f"DEVICE: {device_name}")
                                    print(f"ERROR: {str(e)}")
                                    print(f"{'='*60}")
                                    
                                    step.passx(f"Parsing failed: {str(e)}")
                                    device_last_run[cmd_name] = 0
                                    continue

                                # Save success
                                os.makedirs(f"results/{self.create_time}/{device_name}/success", exist_ok=True)
                                if isinstance(parsed_output, list):
                                    file_path = f"results/{self.create_time}/{device_name}/success/{device_name}_{safe_cmd}_passed.json"
                                    with open(file_path, "w") as f:
                                        json.dump(parsed_output, f, indent=4)
                                else:
                                    file_path = f"results/{self.create_time}/{device_name}/success/{device_name}_{safe_cmd}_no_parser.txt"
                                    with open(file_path, "w") as f:
                                        f.write(parsed_output)
                                
                                # Print raw output to log
                                self.logger.info(f"\n{'='*60}")
                                self.logger.info(f"COMMAND: {cmd_name}")
                                self.logger.info(f"DEVICE: {device_name}")
                                self.logger.info(f"RAW OUTPUT:")
                                self.logger.info(f"{'='*60}")
                                self.logger.info(raw_output)
                                self.logger.info(f"{'='*60}")
                                
                                step.passed(f"Success - Output saved to {file_path}")
                                device_last_run[cmd_name] = now
                                
                            except Exception as e:
                                # Save failure
                                os.makedirs(f"results/{self.create_time}/{device_name}/fail", exist_ok=True)
                                file_path = f"results/{self.create_time}/{device_name}/fail/{device_name}_{safe_cmd}_failed.json"
                                with open(file_path, "w") as f:
                                    json.dump({"error": str(e)}, f, indent=4)
                                
                                self.fails.append({
                                    'device': device_name,
                                    'command': cmd_name,
                                    'result': 'FAIL',
                                    'error': str(e)
                                })
                                
                                # Print error details to log
                                print(f"\n{'='*60}")
                                print(f"COMMAND FAILED: {cmd_name}")
                                print(f"DEVICE: {device_name}")
                                print(f"ERROR: {str(e)}")
                                print(f"{'='*60}")
                                
                                step.passx(f"Failed: {str(e)}")
                                device_last_run[cmd_name] = 0

                    # Update last run times for this device
                    last_run_times[device_name] = device_last_run
                    with open(last_run_file, "w") as f:
                        json.dump(last_run_times, f, indent=4)

            except Exception as e:
                # Device-level failure
                self.fails.append({
                    'device': device_name,
                    'command': "DEVICE_CONNECTION_ERROR",
                    'result': 'FAIL',
                    'error': str(e)
                })
                with steps.start(f"Processing device {device_name}") as step:
                    step.passx(f"Device error: {str(e)}")

    # ---------------------------------------------------
    # Cleanup: Send email report of failures
    # ---------------------------------------------------
    @cleanup
    def collect_and_send(self):
        """Collect failures across run and send summary email"""
        # Disconnect all devices
        self.connection_cleanup()
        
        if self.fails:
            failure_messages = []
            for fail in self.fails:
                msg_parts = []
                if 'command' in fail:
                    msg_parts.append(f"Command: {fail['command']}")
                if 'device' in fail:
                    msg_parts.append(f"Device: {fail['device']}")
                msg_parts.append(f"Error: {fail['error']}")
                message = " | ".join(msg_parts)
                failure_messages.append(message)

            email_body = f"""
            Test Execution Report - {self.create_time}

            Total Failures: {len(self.fails)}

            Detailed Failures:
            {chr(10).join(failure_messages)}

            Please review the files.
            """
            try:
                send_email(email_body)
                self.logger.info("Email sent successfully with failure report")
            except Exception as e:
                self.logger.info(f"Failed to send email: {e}")
        else:
            self.logger.info("No failures detected - all tests passed successfully")

    # ---------------------------------------------------
    # Helper: Disconnect all devices
    # ---------------------------------------------------
    def connection_cleanup(self):
        for device_name, device in self.connected_devices.items():
            try:
                device.disconnect()
            except Exception as e:
                self.logger.warning(f"Error disconnecting {device_name}: {e}")