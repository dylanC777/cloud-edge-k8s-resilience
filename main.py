import yaml
import os
import time
import sys
from ssh_manager import SSHManager
from k8s_controller import K8sController
from load_runner import LoadRunner
from result_manager import ResultManager
from cluster_checker import ClusterChecker

def recover_worker_nodes(ssh_manager):
    try:
        recovery_cmd = "kubectl get nodes | grep -v master | awk '{print $1}' | xargs -I{} kubectl uncordon {} 2>/dev/null || true"
        ssh_manager.run_command(recovery_cmd)
        
        recovery_cmd2 = "for node in $(kubectl get nodes | grep -v master | awk '{print $1}'); do ssh ubuntu@$node 'sudo systemctl start kubelet' 2>/dev/null || true; done"
        ssh_manager.run_command(recovery_cmd2)
        
        print("Worker nodes recovery completed successfully")
        return True
    except Exception as e:
        print(f"Warning: Worker nodes recovery operation failed: {e}")
        return False

def main():
    # Load configuration from config.yaml
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Parse top-level configuration values
    master_cfg = config.get('master', {})
    client_cfg = config.get('client', {}) 

    # Clean and normalize result_base path
    raw_base = config.get('result_base', 'results')
    results_base = os.path.normpath(raw_base.strip())

    # Get cluster check options from config
    check_options = config.get('cluster_checks', {})
    skip_checks = check_options.get('skip', False)
    continue_on_fail = check_options.get('continue_on_fail', False)
    wait_for_ready = check_options.get('wait_for_ready', True)
    max_wait_attempts = check_options.get('max_wait_attempts', 30)
    retry_interval = check_options.get('retry_interval', 10)
    locust_retry_count = check_options.get('locust_retry_count', 3)
    
    # Get timeout options from config
    timeout_recovery_seconds = config.get('timeout_recovery_seconds', 60)
    timeout_recovery_seconds = max(timeout_recovery_seconds, 120)
    check_between_timeouts = config.get('check_between_timeouts', True)
    test_duration_minutes = config.get('test_duration_minutes', 10)
    
    experiments = config.get('experiments', [])

    # Get application namespace from config or default to "image-detection"
    app_namespace = config.get('app_namespace', 'image-detection')

    # Initialize SSH connections
    ssh_master = SSHManager(master_cfg.get('host'), master_cfg.get('user'), master_cfg.get('key_path'))
    ssh_client = SSHManager(client_cfg.get('host'), client_cfg.get('user'), client_cfg.get('key_path'))
    try:
        ssh_master.connect()
        print("SSH connection established to master node.")
        ssh_client.connect()
        print("SSH connection established to client node.")
    except Exception as e:
        print(f"Error: SSH connection failed - {e}")
        return

    # Initialize cluster checker and perform health checks
    if not skip_checks:
        checker = ClusterChecker(ssh_master)
        checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
        
        if not checks_passed:
            if wait_for_ready:
                print("Cluster health checks failed. Waiting for cluster to become ready...")
                checks_passed = checker.wait_for_healthy_cluster(
                    app_namespace=app_namespace,
                    max_wait_attempts=max_wait_attempts,
                    retry_interval=retry_interval
                )
                
                if not checks_passed and not continue_on_fail:
                    print("Cluster health checks still failing after maximum wait time. Aborting experiments.")
                    ssh_master.close()
                    ssh_client.close()
                    sys.exit(1)
                elif not checks_passed:
                    print("Cluster health checks still failing after maximum wait time, but continue_on_fail is True. Proceeding with caution.")
            elif not continue_on_fail:
                print("Cluster health checks failed and continue_on_fail is False. Aborting experiments.")
                ssh_master.close()
                ssh_client.close()
                sys.exit(1)
            else:
                print("Cluster health checks failed but continue_on_fail is True. Proceeding with caution.")

    k8s_ctrl = K8sController(ssh_master)

    # Iterate experiments
    for idx, experiment in enumerate(experiments, start=1):
        chaos_yaml_path   = experiment.get('chaos_yaml')
        schedule_name     = experiment.get('delete_schedule')
        locust_script     = experiment.get('locust_script')
        locust_csv_path   = experiment.get('locust_log')
        timeouts          = experiment.get('timeouts', [])
        user_counts       = experiment.get('user_counts', [1]) 
        recovery_wait     = experiment.get('recovery_wait_seconds', 0)
        request_rate      = experiment.get('request_rate', 1.0)
        # Get experiment-specific timeout recovery value or use global default
        timeout_recovery  = experiment.get('timeout_recovery_seconds', timeout_recovery_seconds)

        master_count = experiment.get('master_count', 1)
        worker_count = experiment.get('worker_count', 3)

        is_shell_script = chaos_yaml_path and chaos_yaml_path.endswith('.sh')
        
        if is_shell_script:
            exp_label = os.path.basename(chaos_yaml_path)
        else:
            exp_label = schedule_name or f"experiment_{idx}"
            
        exp_base = os.path.join(results_base, exp_label)
        os.makedirs(exp_base, exist_ok=True)
        result_manager = ResultManager(exp_base)

        load_runner = LoadRunner(ssh_client, locust_script, locust_csv_path)

        if not skip_checks:
            print(f"\n=== RESTARTING DEPLOYMENTS BEFORE EXPERIMENT '{exp_label}' ===")
            checker.restart_deployments(app_namespace=app_namespace)

        # Run health checks before each experiment schedule if configured to do so
        if check_options.get('check_before_each_experiment', False) and not skip_checks:
            print(f"\n=== HEALTH CHECK BEFORE EXPERIMENT '{exp_label}' ===")
            checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
            
            if not checks_passed:
                if wait_for_ready:
                    print(f"Health checks before experiment '{exp_label}' failed. Waiting for cluster to become ready...")
                    checks_passed = checker.wait_for_healthy_cluster(
                        app_namespace=app_namespace,
                        max_wait_attempts=max_wait_attempts,
                        retry_interval=retry_interval
                    )
                    
                    if not checks_passed and not continue_on_fail:
                        print(f"Skipping experiment '{exp_label}' due to failed health checks after maximum wait time")
                        continue
                    elif not checks_passed:
                        print(f"Proceeding with experiment '{exp_label}' despite failed health checks (continue_on_fail=True)")
                elif not continue_on_fail:
                    print(f"Skipping experiment '{exp_label}' due to failed health checks")
                    continue
                else:
                    print(f"Proceeding with experiment '{exp_label}' despite failed health checks (continue_on_fail=True)")

        # apply chaos
        try:
            print(f"Applying chaos experiment: {chaos_yaml_path}")
            k8s_ctrl.apply_chaos_experiment(chaos_yaml_path)
        except Exception as e:
            print(f"Error applying chaos experiment for '{exp_label}': {e}")
            continue

        for user_count in user_counts:
            user_exp_base = os.path.join(exp_base, f"users_{user_count}")
            os.makedirs(user_exp_base, exist_ok=True)

            if request_rate == -1:
                rate_exp_base = os.path.join(user_exp_base, "concurrent_mode")
            elif request_rate == -2:
                rate_exp_base = os.path.join(user_exp_base, "piggyback_mode")
            else:
                rate_exp_base = os.path.join(user_exp_base, f"rate_{request_rate}s")
                
            os.makedirs(rate_exp_base, exist_ok=True)
            user_result_manager = ResultManager(rate_exp_base)

            print(f"\n=== RUNNING TESTS WITH {user_count} CONCURRENT USERS ===")

            for timeout_idx, timeout in enumerate(timeouts):
                try:
                    print(f"=== Running '{exp_label}' with {user_count} users and timeout {timeout}s ===")
                    
                    # Try to run the Locust test with retries
                    success = False
                    locust_error = None
                    for retry_num in range(1, locust_retry_count + 1):
                        try:
                            if retry_num > 1:
                                print(f"Retrying Locust test (attempt {retry_num}/{locust_retry_count})...")
                            
                            load_runner.run_test(
                                timeout_value=timeout, 
                                user_count=user_count, 
                                test_duration_minutes=test_duration_minutes,
                                rate_interval=request_rate
                            )
                            success = True
                            break
                        except Exception as e:
                            locust_error = e
                            print(f"Locust test attempt {retry_num} failed: {e}")
                            
                            # Wait a bit before retrying
                            if retry_num < locust_retry_count:
                                print(f"Waiting 5 seconds before retry...")
                                time.sleep(5)
                    
                    # If all retries failed, raise the last error
                    if not success:
                        raise Exception(f"All {locust_retry_count} Locust test attempts failed. Last error: {locust_error}")
                    
                    timestamp  = time.strftime("%Y%m%dT%H%M%S")
                    result_dir = os.path.join(rate_exp_base, f"timeout_{timeout}s_{timestamp}")
                    os.makedirs(result_dir, exist_ok=True)
                    print(f"Created result directory: {result_dir}")

                    # 1) copy chaos yaml/script (local)
                    try:
                        user_result_manager.copy_chaos_config(chaos_yaml_path, result_dir)
                    except Exception as e:
                        print(f"[Warning] copy chaos_config fail: {e}")

                    # 2) download CSV log
                    try:
                        user_result_manager.download_csv_log(ssh_client, locust_csv_path, result_dir)
                    except Exception as e:
                        print(f"[Warning] download CSV fail: {e}")

                    # 3) download console log
                    try:
                        user_result_manager.download_console_log(ssh_client, load_runner.console_log_path, result_dir)
                    except Exception as e:
                        print(f"[Warning] download console log fail: {e}")

                    # 4) generate report
                    metadata = {
                        "user_count": user_count,
                        "timeout": timeout,
                        "test_duration_minutes": test_duration_minutes
                    }
                    
                    if request_rate == -1:
                        metadata["request_mode"] = "concurrent"
                    elif request_rate == -2:
                        metadata["request_mode"] = "piggyback" 
                    else:
                        metadata["request_rate"] = request_rate
                        
                    user_result_manager.generate_report(timeout, locust_script, result_dir, metadata=metadata)

                    # 5) create summary CSV
                    try:
                        user_result_manager.create_summary_csv(
                            result_dir, 
                            schedule_name=schedule_name if not is_shell_script else os.path.basename(chaos_yaml_path),
                            master_count=master_count,
                            worker_count=worker_count
                        )
                    except Exception as e:
                        print(f"[Warning] create summary CSV fail: {e}")

                    print(f"Results for {user_count} users and timeout {timeout}s saved in {result_dir}")
                    
                    if timeout_idx < len(timeouts) - 1:
                        # Delete current chaos schedule
                        if is_shell_script:
                            print(f"Shell script experiment: {exp_label}, performing node recovery between timeout tests...")
                            recover_worker_nodes(ssh_master)
                        elif schedule_name:
                            try:
                                k8s_ctrl.delete_chaos_experiment(schedule_name)
                                print(f"Deleted chaos schedule '{schedule_name}' to reset chaos.")
                            except Exception as e_del:
                                print(f"Error deleting schedule '{schedule_name}': {e_del}")
                        else:
                            print("No schedule name provided, skipping chaos deletion.")
                        
                        print(f"\n=== WAITING BETWEEN TIMEOUT TESTS WITHOUT DEPLOYMENT RESTART ===")
                        print(f"Waiting {timeout_recovery}s for recovery between timeout tests...")
                        time.sleep(timeout_recovery)
                        
                        if check_between_timeouts and not skip_checks:
                            print(f"\n=== HEALTH CHECK BETWEEN TIMEOUT TESTS ({timeout}s -> {timeouts[timeout_idx + 1]}s) ===")
                            timeout_checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
                            if not timeout_checks_passed and wait_for_ready:
                                print(f"Health checks between timeout tests failed. Waiting for cluster to become ready...")
                                checker.wait_for_healthy_cluster(
                                    app_namespace=app_namespace,
                                    max_wait_attempts=max_wait_attempts,
                                    retry_interval=retry_interval
                                )
                        # Re-apply chaos experiment for next timeout test
                        try:
                            k8s_ctrl.apply_chaos_experiment(chaos_yaml_path)
                            print("Chaos experiment reapplied for next timeout test.")
                        except Exception as e_app:
                            print(f"Error reapplying chaos experiment for next timeout: {e_app}")
                            break
                    
                except Exception as e:
                    print(f"Error during timeout {timeout}s with {user_count} users in '{exp_label}': {e}")
                    
                    # After a failed timeout test, still perform chaos reset and recovery steps
                    if timeout_idx < len(timeouts) - 1:
                        if is_shell_script:
                            print(f"Shell script experiment: {exp_label}, performing node recovery after failed test...")
                            recover_worker_nodes(ssh_master)
                        elif schedule_name:
                            try:
                                k8s_ctrl.delete_chaos_experiment(schedule_name)
                                print(f"Deleted chaos schedule '{schedule_name}' after failed timeout.")
                            except Exception as e_del:
                                print(f"Error deleting schedule '{schedule_name}' after failure: {e_del}")
                        else:
                            print("No schedule name provided, skipping chaos deletion after failure.")
                        
                        print(f"Waiting {timeout_recovery}s for recovery after failed timeout test...")
                        time.sleep(timeout_recovery)
                        
                        if check_between_timeouts and not skip_checks:
                            print(f"\n=== HEALTH CHECK AFTER FAILED TIMEOUT TEST ===")
                            checker.perform_all_checks(app_namespace=app_namespace)
                        try:
                            k8s_ctrl.apply_chaos_experiment(chaos_yaml_path)
                            print("Chaos experiment reapplied for next timeout test after failure.")
                        except Exception as e_app:
                            print(f"Error reapplying chaos experiment after failed timeout: {e_app}")
                            break
                    continue

            if is_shell_script:
                print(f"Shell script experiment: {exp_label}, performing node recovery after user count tests...")
                recover_worker_nodes(ssh_master)
            elif schedule_name:
                try:
                    k8s_ctrl.delete_chaos_experiment(schedule_name)
                    print(f"Deleted chaos schedule '{schedule_name}' after user count {user_count} tests.")
                except Exception as e:
                    print(f"Error deleting schedule '{schedule_name}': {e}")

            if user_count != user_counts[-1]:
                if not skip_checks:
                    print(f"\n=== RESTARTING DEPLOYMENTS BEFORE NEXT USER COUNT {user_counts[user_counts.index(user_count) + 1]} ===")
                    checker.restart_deployments(app_namespace=app_namespace)

                print(f"Waiting {recovery_wait}s for system recovery between user count tests...")
                time.sleep(recovery_wait)
                
                # Run health check after recovery
                if not skip_checks:
                    print(f"\n=== HEALTH CHECK BEFORE NEXT USER COUNT ===")
                    checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
                    if not checks_passed and wait_for_ready:
                        print(f"Health checks before next user count failed. Waiting for cluster to recover...")
                        checker.wait_for_healthy_cluster(
                            app_namespace=app_namespace,
                            max_wait_attempts=max_wait_attempts,
                            retry_interval=retry_interval
                        )
            
            if user_count != user_counts[-1]:
                try:
                    k8s_ctrl.apply_chaos_experiment(chaos_yaml_path)
                    print(f"Reapplied chaos experiment for next user count {user_counts[user_counts.index(user_count) + 1]}.")
                except Exception as e:
                    print(f"Error reapplying chaos experiment for next user count: {e}")
                    break

        # cleanup schedule at the end of all user counts
        if is_shell_script:
            print(f"Shell script experiment: {exp_label}, performing node recovery at the end of experiment...")
            recover_worker_nodes(ssh_master)
        elif schedule_name:
            try:
                k8s_ctrl.delete_chaos_experiment(schedule_name)
            except Exception as e:
                print(f"Error deleting schedule '{schedule_name}': {e}")

        if not skip_checks:
            print(f"\n=== RESTARTING DEPLOYMENTS AFTER EXPERIMENT '{exp_label}' ===")
            checker.restart_deployments(app_namespace=app_namespace)
            
        # wait for recovery between experiments
        if isinstance(recovery_wait, (int, float)) and recovery_wait > 0:
            print(f"Waiting {recovery_wait}s for system recovery between experiments...")
            time.sleep(recovery_wait)

            # Run health check after recovery if configured to do so
            if check_options.get('check_after_recovery', True) and not skip_checks:
                print(f"\n=== HEALTH CHECK AFTER EXPERIMENT '{exp_label}' ===")
                checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
                
                # If not healthy and wait_for_ready is enabled, wait for recovery
                if not checks_passed and wait_for_ready:
                    print(f"Post-experiment health checks for '{exp_label}' failed. Waiting for cluster to recover...")
                    checker.wait_for_healthy_cluster(
                        app_namespace=app_namespace,
                        max_wait_attempts=max_wait_attempts,
                        retry_interval=retry_interval
                    )

    # Clean up client files to free disk space
    try:
        print("\nCleaning up logs on client node to prevent disk space issues...")
        cleanup_cmd = "rm -f /home/ubuntu/*.csv /home/ubuntu/*.log /home/ubuntu/console_output.log"
        ssh_client.run_command(cleanup_cmd)
    except Exception as e:
        print(f"Warning: Failed to clean up client logs: {e}")

    print("\n=== FINAL SYSTEM RECOVERY ===")
    recover_worker_nodes(ssh_master)

    # close SSH
    ssh_master.close()
    ssh_client.close()
    print("All experiments completed.")

if __name__ == "__main__":
    main()