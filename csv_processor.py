import os
import re
import csv
import yaml
import json

class CSVProcessor:
    """Processes experiment result CSV files and generates summarized versions with metadata."""
    
    def __init__(self):
        pass
        
    def extract_metrics_from_console_log(self, console_log_path):
        """Extract key metrics from Locust console output logs and also check CSV file for error types."""
        metrics = {
            'total_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'error_occurrences': 0,
            'error_messages': [],
            'error_counts': {},
            'error_message': ""
        }
        
        try:
            with open(console_log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Find all aggregate metrics lines
                agg_pattern = r'Aggregated\s+(\d+)\s+(\d+)\(\d+\.\d+%\)\s*\|\s*(\d+)'
                agg_matches = re.findall(agg_pattern, content)
                
                # Use the last match (final result)
                if agg_matches:
                    last_match = agg_matches[-1]
                    metrics['total_requests'] = int(last_match[0])
                    metrics['failed_requests'] = int(last_match[1])
                    metrics['avg_response_time'] = float(last_match[2])
                
                # Find all error types and their occurrence counts
                error_pattern = r'(\d+)\s+POST /api/imagedetect: (.+)'
                error_matches = re.findall(error_pattern, content)
                
                total_error_occurrences = 0
                if error_matches:
                    for count_str, error_msg in error_matches:
                        count = int(count_str)
                        error_msg = error_msg.strip()
                        
                        # Add to the list of all errors
                        metrics['error_messages'].append(f"{count} × {error_msg}")
                        
                        # Add to the counts dictionary
                        if error_msg in metrics['error_counts']:
                            metrics['error_counts'][error_msg] += count
                        else:
                            metrics['error_counts'][error_msg] = count
                                
                        total_error_occurrences += count
                    
                    # Set the overall error occurrence count
                    metrics['error_occurrences'] = total_error_occurrences
                    
                    # For backward compatibility, use the first error as the main error message
                    if error_matches and not metrics['error_message']:
                        metrics['error_message'] = error_matches[0][1].strip()
        
        except Exception as e:
            print(f"Error extracting metrics from console log: {e}")
        
        # if there are failed requests but no error messages, try to extract errors from CSV
        if metrics['failed_requests'] > 0 and not metrics['error_messages']:
            result_dir = os.path.dirname(console_log_path)
            csv_path = os.path.join(result_dir, "locust_log.csv")
            
            # if the main CSV file does not exist, try to find any CSV file in the directory
            if not os.path.exists(csv_path):
                # check for any CSV files in the result directory
                csv_files = [f for f in os.listdir(result_dir) if f.endswith('.csv') and not f.endswith('_summary.csv')]
                if csv_files:
                    csv_path = os.path.join(result_dir, csv_files[0])
                    print(f"Using CSV file: {csv_path}")
            
            # if the CSV file exists, try to extract error information
            if os.path.exists(csv_path):
                try:
                    print(f"Extracting error information from CSV file: {csv_path}")
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        csv_reader = csv.reader(f)
                        headers = next(csv_reader)
                        
                        error_idx = None
                        status_idx = None
                        
                        for i, header in enumerate(headers):
                            if header.lower() in ('error type', 'error'):
                                error_idx = i
                            elif header.lower() == 'status':
                                status_idx = i
                        
                        if error_idx is not None and status_idx is not None:
                            error_types = {}
                            
                            for row in csv_reader:
                                if len(row) > error_idx and len(row) > status_idx:
                                    status = row[status_idx].strip()
                                    
                                    if status.lower() in ('error', 'failure', 'fail'):
                                        error_text = row[error_idx].strip()
                                        if error_text:
                                            if "ReadTimeout" in error_text:
                                                error_type = "ReadTimeout"
                                            elif "ConnectionError" in error_text:
                                                error_type = "ConnectionError"
                                            else:
                                                match = re.search(r'([A-Za-z]+)(Error|Timeout|Exception)', error_text)
                                                if match:
                                                    error_type = match.group(0)
                                                else:
                                                    error_type = error_text[:30] + "..." if len(error_text) > 30 else error_text
                                            
                                            if error_type in error_types:
                                                error_types[error_type] += 1
                                            else:
                                                error_types[error_type] = 1
                            
                            if error_types:
                                metrics['error_occurrences'] = sum(error_types.values())
                                
                                for error_type, count in error_types.items():
                                    metrics['error_messages'].append(f"{count} × {error_type}")
                                    metrics['error_counts'][error_type] = count
                                
                                if not metrics['error_message'] and error_types:
                                    most_common_error = max(error_types.items(), key=lambda x: x[1])[0]
                                    metrics['error_message'] = most_common_error
                                
                                print(f"Found {metrics['error_occurrences']} errors in CSV file")
                except Exception as e:
                    print(f"Error processing CSV file: {e}")
                    import traceback
                    traceback.print_exc()
        
        return metrics

    def count_unique_users_in_csv(self, csv_file_path):
        """Count unique user IDs in the CSV log file."""
        unique_users = set()
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                headers = next(csv_reader)  # Skip header row
                
                # Find the index of the User ID column
                user_id_idx = None
                for idx, header in enumerate(headers):
                    if header.lower() in ('user id', 'user_id', 'userid'):
                        user_id_idx = idx
                        break
                
                if user_id_idx is None:
                    print(f"Warning: No 'User ID' column found in {csv_file_path}")
                    return 0
                
                # Count unique user IDs
                for row in csv_reader:
                    if len(row) > user_id_idx:
                        user_id = row[user_id_idx].strip()
                        if user_id:
                            unique_users.add(user_id)
            
            return len(unique_users)
        except Exception as e:
            print(f"Error counting unique users in CSV: {e}")
            return 0

    def extract_experiment_info(self, result_dir, schedule_name=None, master_count=1, worker_count=3):
        """Extract experiment information from directory structure and YAML file."""
        info = {
            'experiment_name': schedule_name or "unknown",
            'app': "image-detection",
            'timeout': 0,
            'master_nodes': master_count,
            'worker_nodes': worker_count,
            'user_count': 0,  # Default value, will be updated if metadata or CSV has user count info
            'request_rate': 1.0
        }
        
        # Check for metadata.json (preferred source for user count and request mode)
        metadata_path = os.path.join(result_dir, "metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    if 'user_count' in metadata:
                        info['user_count'] = metadata['user_count']
                    if 'request_rate' in metadata:
                        info['request_rate'] = metadata['request_rate']
                    if 'request_mode' in metadata:
                        if metadata['request_mode'] == 'concurrent':
                            info['request_rate'] = -1
                        elif metadata['request_mode'] == 'piggyback':
                            info['request_rate'] = -2
            except Exception as e:
                print(f"Error reading metadata.json: {e}")
        
        # If no user count in metadata, try to extract it from CSV
        if info['user_count'] == 0:
            csv_path = os.path.join(result_dir, "locust_log.csv")
            if os.path.exists(csv_path):
                info['user_count'] = self.count_unique_users_in_csv(csv_path)
        
        if schedule_name and schedule_name.endswith('.sh'):
            info['experiment_name'] = os.path.basename(schedule_name)
            info['experiment_type'] = 'shell_script'
        # If schedule_name not provided, get experiment name from parent directory
        elif not schedule_name:
            parent_dir = os.path.basename(os.path.dirname(result_dir))
            if parent_dir:
                info['experiment_name'] = parent_dir
        
        # Get timeout value from directory name
        dir_name = os.path.basename(result_dir)
        timeout_match = re.search(r'timeout_(\d+\.?\d*)s', dir_name)
        if timeout_match:
            info['timeout'] = float(timeout_match.group(1))
        
        rate_dir = os.path.basename(os.path.dirname(result_dir))
        if rate_dir == "concurrent_mode":
            info['request_rate'] = -1
        elif rate_dir == "piggyback_mode":
            info['request_rate'] = -2
        elif rate_dir.startswith("rate_") and rate_dir.endswith("s"):
            try:
                rate_value = rate_dir.replace("rate_", "").replace("s", "")
                info['request_rate'] = float(rate_value)
            except ValueError:
                pass
        
        # Try to extract cluster information from chaos_config.yaml
        chaos_config_path = os.path.join(result_dir, "chaos_config.yaml")
        if os.path.exists(chaos_config_path):
            try:
                with open(chaos_config_path, 'r') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("#!"):
                        info['chaos_type'] = 'shell_script'
                    else:
                        f.seek(0)
                        try:
                            chaos_config = yaml.safe_load(f)
                            info['chaos_type'] = 'yaml'
                        except Exception:
                            info['chaos_type'] = 'unknown'
            except Exception as e:
                print(f"Error reading chaos configuration: {e}")
        
        return info

    def create_summary_csv(self, original_csv_path, result_dir, console_log_path, 
                          schedule_name=None, master_count=1, worker_count=3):
        """Create a new summary CSV file with experiment information and original data."""
        # Create output path by adding _summary suffix to original filename
        file_name, file_ext = os.path.splitext(original_csv_path)
        summary_csv_path = f"{file_name}_summary{file_ext}"
        
        # Extract information
        experiment_info = self.extract_experiment_info(
            result_dir, 
            schedule_name=schedule_name,
            master_count=master_count,
            worker_count=worker_count
        )
        metrics = self.extract_metrics_from_console_log(console_log_path)
        
        # Calculate both overall average response time and successful response time from CSV
        total_requests = 0
        total_success = 0
        sum_all_rt = 0.0
        sum_success_rt = 0.0
        
        try:
            with open(original_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Count all requests and sum their response times
                    total_requests += 1
                    rt_field = None
                    
                    if 'Response Time (ms)' in row:
                        rt_field = 'Response Time (ms)'
                    elif 'Response Time' in row:
                        rt_field = 'Response Time'
                    
                    if rt_field and row[rt_field]:
                        try:
                            rt = float(row[rt_field])
                            sum_all_rt += rt
                            
                            status_field = None
                            if 'Status' in row:
                                status_field = 'Status'
                            elif 'status' in row:
                                status_field = 'status'
                                
                            if status_field and row[status_field].strip().lower() == 'success':
                                total_success += 1
                                sum_success_rt += rt
                        except (ValueError, TypeError):
                            print(f"Warning: Could not convert response time value: {row[rt_field]}")
            
            # Calculate averages
            csv_avg_all_rt = (sum_all_rt / total_requests) if total_requests > 0 else 0.0
            csv_avg_success_rt = (sum_success_rt / total_success) if total_success > 0 else 0.0
            
            # Use CSV calculated successful average response time
            metrics['avg_success_response_time'] = csv_avg_success_rt
            
            # For debugging: print comparison between console log and CSV calculations
            print(f"Debug - Total requests comparison: Console={metrics['total_requests']}, CSV={total_requests}")
            print(f"Debug - Failed requests in Console: {metrics['failed_requests']}")
            print(f"Debug - Success requests in CSV: {total_success}")
            print(f"Debug - Overall average RT: Console={metrics['avg_response_time']}, CSV={csv_avg_all_rt:.2f}")
            print(f"Debug - Success average RT from CSV: {csv_avg_success_rt:.2f}")
            
            if metrics['failed_requests'] == 0:
                print("Notice: No failures detected, setting successful response time equal to overall average")
                metrics['avg_success_response_time'] = metrics['avg_response_time']
            else:
                metrics['avg_success_response_time'] = csv_avg_success_rt
                print(f"Notice: {metrics['failed_requests']} failures detected, using CSV calculated average successful response time: {csv_avg_success_rt:.2f} ms")
        
        except Exception as e:
            print(f"Error calculating response times from CSV: {e}")
            import traceback
            traceback.print_exc()
        
        with open(summary_csv_path, 'w', encoding='utf-8', newline='') as summary_file:
            writer = csv.writer(summary_file)
            
            # Write metadata
            writer.writerow(["# Experiment Name:", experiment_info['experiment_name']])
            writer.writerow(["# Application:", experiment_info['app']])
            writer.writerow(["# Timeout (s):", experiment_info['timeout']])
            writer.writerow(["# Master Nodes:", experiment_info['master_nodes']])
            writer.writerow(["# Worker Nodes:", experiment_info['worker_nodes']])
            writer.writerow(["# User Count:", experiment_info['user_count']])
            
            if 'request_rate' in experiment_info:
                if experiment_info['request_rate'] == -1:
                    writer.writerow(["# Request Mode:", "Concurrent (No Rate Limit)"])
                elif experiment_info['request_rate'] == -2:
                    writer.writerow(["# Request Mode:", "Piggyback"])
                else:
                    writer.writerow(["# Request Rate (req/s):", f"1/{experiment_info['request_rate']}"])
            else:
                writer.writerow(["# Request Rate (req/s):", "Unknown"])
            
            if 'experiment_type' in experiment_info and experiment_info['experiment_type'] == 'shell_script':
                writer.writerow(["# Experiment Type:", "Shell Script"])
            elif 'chaos_type' in experiment_info:
                writer.writerow(["# Chaos Type:", experiment_info['chaos_type']])
            
            writer.writerow(["# Total Requests:", metrics['total_requests']])
            writer.writerow(["# Failed Requests:", metrics['failed_requests']])
            writer.writerow(["# Average Response Time (ms):", round(metrics['avg_response_time'], 2)])
            writer.writerow([
                "# Average Successful Response Time (ms):",
                round(metrics['avg_success_response_time'], 2)
            ])
            writer.writerow(["# Total Error Occurrences:", metrics['error_occurrences']])
            
            # Write all error types and their occurrences
            if metrics['error_messages']:
                writer.writerow(["# Error Types:"])
                for error_msg in metrics['error_messages']:
                    writer.writerow(["#   " + error_msg])
            else:
                writer.writerow(["# Error Types:", "None"])
                
            writer.writerow([])  # Add empty line before original content
            
            # If original CSV exists, append its content
            if os.path.exists(original_csv_path):
                try:
                    with open(original_csv_path, 'r', encoding='utf-8') as original:
                        # Read original CSV content
                        reader = csv.reader(original)
                        # Write each row to the summary file
                        for row in reader:
                            writer.writerow(row)
                except Exception as e:
                    print(f"Error appending original CSV content: {e}")
            
        print(f"Successfully created summary CSV file: {summary_csv_path}")
        return summary_csv_path

    def process_result_directory(self, result_dir, schedule_name=None, master_count=1, worker_count=3):
        """Process a single result directory."""
        rate_dir = os.path.basename(os.path.dirname(result_dir))
        is_piggyback = (rate_dir == "piggyback_mode")
        
        console_log_path = os.path.join(result_dir, "console_output.log")
        
        if is_piggyback:
            piggyback_csv = os.path.join(result_dir, "locust_log_piggyback_timeout.csv")
            if os.path.exists(piggyback_csv):
                original_csv_path = piggyback_csv
                print(f"Found piggyback mode CSV file: {original_csv_path}")
            else:
                original_csv_path = os.path.join(result_dir, "locust_log.csv")
        else:
            original_csv_path = os.path.join(result_dir, "locust_log.csv")
        
        csv_exists = os.path.exists(original_csv_path)
        log_exists = os.path.exists(console_log_path)
        
        if not csv_exists:
            print(f"Warning: Primary CSV file not found at {original_csv_path}")
            all_files = os.listdir(result_dir)
            csv_files = [f for f in all_files if f.endswith('.csv')]
            if csv_files:
                print(f"Found alternative CSV files: {csv_files}")
                original_csv_path = os.path.join(result_dir, csv_files[0])
                csv_exists = True
                print(f"Using alternative CSV file: {original_csv_path}")
        
        if not log_exists:
            print(f"Warning: Console log not found at {console_log_path}")
            all_files = os.listdir(result_dir)
            log_files = [f for f in all_files if f.endswith('.log')]
            if log_files:
                print(f"Found alternative log files: {log_files}")
                console_log_path = os.path.join(result_dir, log_files[0])
                log_exists = True
                print(f"Using alternative log file: {console_log_path}")
        
        if csv_exists and log_exists:
            try:
                print(f"Creating summary CSV for {rate_dir} mode using:")
                print(f"  - CSV: {original_csv_path}")
                print(f"  - Log: {console_log_path}")
                print(f"  - Schedule: {schedule_name}")
                
                summary_path = self.create_summary_csv(
                    original_csv_path, 
                    result_dir, 
                    console_log_path,
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
                import traceback
                traceback.print_exc()
        else:
            print(f"Required log files missing in {result_dir}")
            return None