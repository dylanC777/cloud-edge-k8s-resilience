import os
import shutil
import time
import json
from csv_processor import CSVProcessor

class ResultManager:
    """Organizes results into folders and generates reports."""
    def __init__(self, base_results_path):
        self.base_results_path = base_results_path
        os.makedirs(self.base_results_path, exist_ok=True)
        self.csv_processor = CSVProcessor()

    def create_result_dir(self, experiment_dir, timeout_value, request_rate=None):
        """Create a subdirectory inside the given experiment_dir named after the timeout (e.g., "timeout_5s_20250420T123456")."""
        timestamp = time.strftime("%Y%m%dT%H%M%S")
        folder_name = f"timeout_{timeout_value}s_{timestamp}"
        result_dir = os.path.join(experiment_dir, folder_name)
        os.makedirs(result_dir, exist_ok=True)
        print(f"Created result directory: {result_dir}")
        return result_dir

    def copy_chaos_config(self, chaos_yaml_path, result_dir):
        """Copy the chaos YAML file into the result directory (named chaos_config.yaml)."""
        dest_path = os.path.join(result_dir, "chaos_config.yaml")
        try:
            shutil.copy(chaos_yaml_path, dest_path)
            print(f"Copied chaos config to: {dest_path}")
        except Exception as e:
            print(f"Failed to copy chaos config: {e}")

    def download_csv_log(self, ssh_manager, remote_csv_path, result_dir):
        """Download the CSV log file from the remote host to the result directory."""
        local_csv = os.path.join(result_dir, "locust_log.csv")
        print(f"Attempting to download CSV from remote '{remote_csv_path}' to local '{local_csv}'...")
        
        check_cmd = f"[ -f {remote_csv_path} ] && stat -c %s {remote_csv_path} || echo 'Not Found'"
        try:
            _, size_output, _ = ssh_manager.run_command(check_cmd)
            if 'Not Found' in size_output:
                print(f"Warning: Remote CSV file '{remote_csv_path}' does not exist")
                return
                
            try:
                # ssh_manager.download_file(remote_csv_path, local_csv, timeout=300)
                ssh_manager.download_file(remote_csv_path, local_csv)
                if os.path.exists(local_csv):
                    file_size = os.path.getsize(local_csv)
                    print(f"CSV log downloaded successfully: {local_csv} ({file_size} bytes)")
                else:
                    print("Warning: CSV log does not exist after download.")
            except Exception as e:
                print(f"Error downloading CSV log: {e}")
                
                print("Attempting alternative CSV download method...")
                try:
                    tmp_path = f"/tmp/csv_partial_{int(time.time())}.csv"
                    head_cmd = f"head -n 1 {remote_csv_path} > {tmp_path} && tail -n 5000 {remote_csv_path} >> {tmp_path}"
                    ssh_manager.run_command(head_cmd)
                    ssh_manager.download_file(tmp_path, local_csv)
                    ssh_manager.run_command(f"rm -f {tmp_path}")
                    
                    if os.path.exists(local_csv):
                        print(f"Partial CSV log downloaded using alternative method: {local_csv}")
                    else:
                        print("Warning: Alternative CSV download method failed.")
                except Exception as alt_e:
                    print(f"Alternative CSV download method failed: {alt_e}")
        except Exception as e:
            print(f"Error checking remote CSV file: {e}")

    def download_console_log(self, ssh_manager, remote_log_path, result_dir):
        """Download the console output log from the remote host to the result directory."""
        local_log = os.path.join(result_dir, "console_output.log")
        print(f"Attempting to download console log from remote '{remote_log_path}' to local '{local_log}'...")
        
        try:
            size_cmd = f"[ -f {remote_log_path} ] && stat -c %s {remote_log_path} || echo 'Not Found'"
            _, size_output, _ = ssh_manager.run_command(size_cmd)
            
            if 'Not Found' in size_output:
                print(f"Warning: Remote log file '{remote_log_path}' does not exist")
                return
                
            file_size = 0
            try:
                file_size = int(size_output.strip())
            except (ValueError, TypeError):
                print(f"Could not determine file size from: {size_output}")
                
            if file_size > 1000000:
                print(f"Console log is large ({file_size} bytes), downloading only head and tail portions...")
                
                tmp_path = f"/tmp/log_partial_{int(time.time())}.log"
                head_tail_cmd = (
                    f"echo '=== LOG HEAD (FIRST 50 LINES) ===\n' > {tmp_path} && "
                    f"head -n 50 {remote_log_path} >> {tmp_path} && "
                    f"echo '\n\n=== LOG MIDDLE OMITTED ===\n\n' >> {tmp_path} && "
                    f"echo '=== LOG TAIL (LAST 300 LINES) ===\n' >> {tmp_path} && "
                    f"tail -n 300 {remote_log_path} >> {tmp_path}"
                )
                ssh_manager.run_command(head_tail_cmd)
                
                ssh_manager.download_file(tmp_path, local_log)
                ssh_manager.run_command(f"rm -f {tmp_path}")
                
                if os.path.exists(local_log):
                    print(f"Partial console log downloaded: {local_log}")
                else:
                    print("Warning: Partial console log download failed.")
            else:
                ssh_manager.download_file(remote_log_path, local_log)
                if os.path.exists(local_log):
                    print(f"Console log downloaded successfully: {local_log}")
                else:
                    print("Warning: Console log does not exist after download.")
        except Exception as e:
            print(f"Error downloading console log: {e}")
            
            print("Attempting to download only critical parts of the log...")
            try:
                tmp_path = f"/tmp/log_critical_{int(time.time())}.log"
                critical_cmd = (
                    f"echo '=== CRITICAL LOG PARTS ===\n' > {tmp_path} && "
                    f"grep -E 'Error|Exception|WARNING|CRITICAL|run-time limit|Shutting down|Aggregated|percentiles|occurrences' "
                    f"{remote_log_path} | tail -n 300 >> {tmp_path}"
                )
                ssh_manager.run_command(critical_cmd)
                ssh_manager.download_file(tmp_path, local_log)
                ssh_manager.run_command(f"rm -f {tmp_path}")
                
                if os.path.exists(local_log):
                    print(f"Critical parts of console log downloaded: {local_log}")
            except Exception as alt_e:
                print(f"Alternative console log download method failed: {alt_e}")

    def generate_report(self, timeout_value, locust_script_path, result_dir, metadata=None):
        """Create a Markdown report file summarizing the run with additional metadata."""
        report_path = os.path.join(result_dir, "report.md")
        script_name = os.path.basename(locust_script_path)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# Experiment Report: Timeout {timeout_value}s\n\n")
            
            if metadata:
                f.write("## Test Configuration\n")
                for key, value in metadata.items():
                    f.write(f"- **{key.replace('_', ' ').title()}**: {value}\n")
                f.write("\n")
            
            f.write("## Basic Information\n")
            f.write(f"- **Timeout (s)**: {timeout_value}\n")
            f.write(f"- **Chaos Experiment**: chaos_config.yaml\n")
            f.write(f"- **Locust Script**: {script_name}\n")
            f.write(f"- **Locust Log CSV**: locust_log.csv\n")
            f.write(f"- **Console Log**: console_output.log\n")
            
            if metadata:
                meta_path = os.path.join(result_dir, "metadata.json")
                try:
                    with open(meta_path, 'w', encoding='utf-8') as meta_file:
                        json.dump(metadata, meta_file, indent=2)
                    f.write(f"\n*all saved in [metadata.json]({os.path.basename(meta_path)})*\n")
                except Exception as e:
                    f.write(f"\n*Error in saving: {e}*\n")
                    
        print(f"Report generated at: {report_path}")

    def create_summary_csv(self, result_dir, schedule_name=None, master_count=1, worker_count=3):
        """Create a summary CSV file with experiment metadata and performance metrics."""
        original_csv_path = os.path.join(result_dir, "locust_log.csv")
        console_log_path = os.path.join(result_dir, "console_output.log")
        
        csv_exists = os.path.exists(original_csv_path)
        log_exists = os.path.exists(console_log_path)
        
        if not csv_exists:
            print(f"Warning: CSV file not found at {original_csv_path}")
        
        if not log_exists:
            print(f"Warning: Console log not found at {console_log_path}")
        
        if csv_exists and log_exists:
            try:
                summary_path = self.csv_processor.process_result_directory(
                    result_dir, 
                    schedule_name=schedule_name,
                    master_count=master_count,
                    worker_count=worker_count
                )
                if summary_path:
                    print(f"Generated summary CSV file: {summary_path}")
                    return summary_path
                else:
                    print("Warning: Failed to generate summary CSV")
                    return None
            except Exception as e:
                print(f"Error processing result directory: {e}")
                return None
        else:
            print(f"Required log files missing in {result_dir}")
            return None