import os

class LocustRunner:
    """
    Runs Locust load tests on the client node for specified configurations.
    Support for concurrent user testing with configurable user counts.
    """
    def __init__(self, ssh_manager, locust_script_path, locust_csv_path):
        self.ssh = ssh_manager
        self.script_path = locust_script_path
        self.csv_path = locust_csv_path
        
        # Determine the directory where the Locust script resides.
        self.script_dir = os.path.dirname(self.script_path) or "."
        
        # Get the directory of the CSV log and ensure it ends with a slash.
        csv_dir = os.path.dirname(self.csv_path)
        if csv_dir == "":
            csv_dir = "."
        if not csv_dir.endswith("/"):
            csv_dir += "/"
        # Define remote path for the console log (placed in the same directory as the CSV log)
        self.console_log_path = csv_dir + "console_output.log"

        # Define the absolute path to the Locust executable on the client node.
        self.locust_executable = "/home/ubuntu/.local/bin/locust"

    def run_test(self, timeout_value, user_count=1, test_duration_minutes=10, rate_interval=1.0):
        """
        Run the Locust test with the given timeout_value and user_count.
        """
        # Clean up previous run's log files ONLY (console log and CSV):
        cleanup_cmd = f"rm -f {self.console_log_path} {self.csv_path}"
        self.ssh.run_command(cleanup_cmd)

        # We set an extra buffer (e.g., +1 minute) so that if Locust fails to exit
        # after its run-time, 'timeout' will forcibly kill it.
        kill_after_minutes = test_duration_minutes + 1
        kill_after_seconds = int(kill_after_minutes * 60)
        
        # Determine mode based on rate_interval
        is_piggyback = (rate_interval == -2)
        is_concurrent = (rate_interval == -1)
        
        # Set environment variables based on mode
        env_vars = f"env PIGGY_TIMEOUT={timeout_value} "
        
        # For constant rate mode, add rate interval environment variable
        if not is_piggyback and not is_concurrent and rate_interval > 0:
            env_vars += f"CONSTANT_RATE_INTERVAL={rate_interval} "
        
        # Use the correct script and CSV paths based on the mode
        script_path = self.script_path
        csv_path = self.csv_path
        
        # If in piggyback mode, adjust paths if needed
        if is_piggyback and "piggy" not in script_path.lower():
            script_dir = os.path.dirname(script_path)
            script_path = os.path.join(script_dir, "locust_piggy_timeout.py")
            csv_path = os.path.join(os.path.dirname(self.csv_path), "locust_log_piggyback_timeout.csv")
        
        locust_cmd = (
            f"cd {self.script_dir} && "
            f"{env_vars}"
            f"timeout --kill-after=15s {kill_after_seconds}s "
            f"{self.locust_executable} "
            f"-f {os.path.basename(script_path)} "
            f"--headless -u {user_count} "
            f"--run-time {test_duration_minutes}m "
            f"--csv {csv_path.replace('.csv', '')} "
            f"> {self.console_log_path} 2>&1"
        )

        # Determine mode string for logging
        if is_piggyback:
            mode_str = "piggyback mode"
        elif is_concurrent:
            mode_str = "concurrent mode"
        else:
            mode_str = f"rate={rate_interval}s"
            
        print(f"Running Locust test with timeout={timeout_value}s, users={user_count}, {mode_str}, duration={test_duration_minutes}min...")
        print(f"Final command: {locust_cmd}")

        # Execute command remotely
        exit_status, _, _ = self.ssh.run_command(locust_cmd)
        print(f"Locust test command exited with status: {exit_status}")

        # obtain the console output from the remote log file
        tail_cmd = f"tail -n 300 {self.console_log_path}"
        try:
            _, log_content, _ = self.ssh.run_command(tail_cmd)
            print("Locust console log summary:\n" + log_content)
        except Exception as e:
            print(f"Warning: Could not read log tail: {e}")
            log_content = ""

        # check if the test ran to limit
        ran_to_limit = "--run-time limit reached" in log_content or "Shutting down" in log_content

        # Handle exit_status
        if exit_status == 0:
            # clean success
            pass  
        elif exit_status == 1 and ran_to_limit:
            # treated as success despite code 1
            print(f"Warning: Locust exited with code 1 but run-time limit reached; treating as success.")
        else:
            # any other non-zero exit: inspect logs for success indicators
            success_indicators = [
                "Successfully written all response times",
                "All users spawned",
                "Test finished",
                "Shutting down",
                "Percentile response time"
            ]
            has_success_indicator = any(indicator in log_content for indicator in success_indicators)
            has_result_data = bool(log_content.strip()) and ("Request" in log_content or "requests" in log_content)
            
            if has_success_indicator or has_result_data:
                print(f"Warning: Locust exited with code {exit_status} but results seem valid.")
                print(f"Log contains {'success indicators' if has_success_indicator else ''} "
                      f"{'and data' if has_result_data else ''}.")
            else:
                # if the test failed, gather an example error
                error_cmd = f"grep -E 'Error|Exception|CRITICAL|WARNING' {self.console_log_path} | tail -n 10"
                try:
                    _, error_output, _ = self.ssh.run_command(error_cmd)
                    error_lines = error_output.strip().split('\n') if error_output.strip() else []
                except Exception:
                    error_lines = []
                
                error_msg = f"Locust test failed with exit status {exit_status}"
                if error_lines:
                    error_msg += f": {error_lines[0].strip()}"
                
                # double-check script & locust path
                _, _, _ = self.ssh.run_command(f"ls -la {script_path}")
                locust_check_cmd = f"which {self.locust_executable}"
                locust_exit_code, _, _ = self.ssh.run_command(locust_check_cmd)
                if locust_exit_code != 0:
                    error_msg += f". Locust executable not found at {self.locust_executable}"
                raise Exception(error_msg)

        # if log is empty, warn
        if not log_content.strip():
            print("Warning: Locust test exited successfully but produced no output.")
            
            # check if the CSV file exists
            check_csv = f"[ -f {csv_path} ] && echo 'CSV exists' || echo 'CSV missing'"
            _, csv_status, _ = self.ssh.run_command(check_csv)
            
            if "CSV exists" in csv_status:
                # check the CSV file size
                wc_cmd = f"wc -l {csv_path}"
                _, wc_output, _ = self.ssh.run_command(wc_cmd)
                print(f"CSV file stats: {wc_output}")

        print(f"Locust test with timeout={timeout_value}s, users={user_count}, {mode_str} completed.")