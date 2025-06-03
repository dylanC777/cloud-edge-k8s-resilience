import re
import time

class ClusterChecker:
    """Performs pre-experiment health checks on Kubernetes cluster."""

    def __init__(self, ssh_manager):
        self.ssh = ssh_manager

    def check_nodes_ready(self):
        """Check if all Kubernetes nodes are in Ready state."""
        cmd = "kubectl get nodes -o wide"
        print(f"Checking node status with command: {cmd}")
        
        try:
            exit_status, out, err = self.ssh.run_command(cmd)
            if exit_status != 0:
                print(f"Failed to get node status: {err.strip()}")
                return False
                
            # Parse output to check if all nodes are Ready
            lines = out.strip().split('\n')
            if len(lines) < 2:  # Header + at least one node
                print("No nodes found in cluster")
                return False
                
            all_ready = True
            not_ready_nodes = []
            
            # Skip header row
            for i in range(1, len(lines)):
                node_info = lines[i].split()
                if len(node_info) < 2:
                    continue
                    
                node_name = node_info[0]
                status = node_info[1]
                
                if status != "Ready":
                    all_ready = False
                    not_ready_nodes.append(node_name)
            
            if all_ready:
                print("All nodes are in Ready state")
                return True
            else:
                print(f"Some nodes are not Ready: {', '.join(not_ready_nodes)}")
                return False
                
        except Exception as e:
            print(f"Error checking node status: {e}")
            return False

    def check_no_chaos_schedules(self):
        """Check that no Chaos Mesh schedules are currently running."""
        cmd = "kubectl get schedules -n chaos-mesh"
        print(f"Checking for active chaos schedules with command: {cmd}")
        
        try:
            exit_status, out, err = self.ssh.run_command(cmd)
            if exit_status != 0:
                # Check if it's just "No resources found"
                if "No resources found" in err:
                    print("No active chaos schedules found - good to proceed")
                    return True
                print(f"Failed to check chaos schedules: {err.strip()}")
                return False
                
            # If we get output and it's not "No resources", there are schedules running
            if "No resources found" in out:
                print("No active chaos schedules found - good to proceed")
                return True
                
            # Parse output to get schedule names
            lines = out.strip().split('\n')
            if len(lines) > 1:  # Header + at least one schedule
                schedules = []
                for i in range(1, len(lines)):
                    if lines[i].strip():
                        schedule_info = lines[i].split()
                        if schedule_info:
                            schedules.append(schedule_info[0])
                
                print(f"Warning: Found active chaos schedules: {', '.join(schedules)}")
                return False
                
            print("No active chaos schedules found - good to proceed")
            return True
                
        except Exception as e:
            print(f"Error checking chaos schedules: {e}")
            return False

    def check_application_pods(self, namespace="image-detection"):
        """Check if all application pods are running and ready."""
        cmd = f"kubectl get pods -n {namespace}"
        print(f"Checking application pods in namespace '{namespace}' with command: {cmd}")
        
        try:
            exit_status, out, err = self.ssh.run_command(cmd)
            if exit_status != 0:
                print(f"Failed to get pod status: {err.strip()}")
                return False
                
            # Parse output to check pod states
            lines = out.strip().split('\n')
            if len(lines) < 2:  # Header + at least one pod
                print(f"No pods found in namespace {namespace}")
                return False
                
            all_ready = True
            not_ready_pods = []
            
            # Skip header row
            for i in range(1, len(lines)):
                if not lines[i].strip():
                    continue
                    
                pod_info = lines[i].split()
                if len(pod_info) < 3:
                    continue
                    
                pod_name = pod_info[0]
                pod_status = pod_info[2]
                
                # Extract the ready count fraction (e.g., "1/1")
                ready_frac = pod_info[1]
                if ready_frac and '/' in ready_frac:
                    ready_count, total_count = ready_frac.split('/')
                    if ready_count != total_count or pod_status != "Running":
                        all_ready = False
                        not_ready_pods.append(pod_name)
                else:
                    all_ready = False
                    not_ready_pods.append(pod_name)
            
            if all_ready:
                print(f"All pods in namespace '{namespace}' are running and ready")
                return True
            else:
                print(f"Some pods in namespace '{namespace}' are not ready: {', '.join(not_ready_pods)}")
                return False
                
        except Exception as e:
            print(f"Error checking pod status: {e}")
            return False

    def perform_all_checks(self, app_namespace="image-detection"):
        """Perform all cluster health checks and return overall status."""
        print("\n=== PERFORMING PRE-EXPERIMENT CLUSTER HEALTH CHECKS ===\n")
        
        nodes_ready = self.check_nodes_ready()
        no_chaos = self.check_no_chaos_schedules()
        pods_ready = self.check_application_pods(namespace=app_namespace)
        
        all_checks_passed = nodes_ready and no_chaos and pods_ready
        
        print("\n=== CLUSTER HEALTH CHECK SUMMARY ===")
        print(f"Nodes Ready: {'✓' if nodes_ready else '✗'}")
        print(f"No Active Chaos Schedules: {'✓' if no_chaos else '✗'}")
        print(f"Application Pods Ready: {'✓' if pods_ready else '✗'}")
        print(f"Overall Status: {'PASSED' if all_checks_passed else 'FAILED'}")
        print("=====================================\n")
        
        return all_checks_passed
        
    def wait_for_healthy_cluster(self, app_namespace="image-detection", max_wait_attempts=30, retry_interval=10):
        """Wait for cluster to reach a healthy state, retrying up to max_wait_attempts.
        
        Args:
            app_namespace: Namespace of the application to check
            max_wait_attempts: Maximum number of attempts to check
            retry_interval: Seconds to wait between retries
            
        Returns:
            bool: True if cluster became healthy, False if max_wait_attempts reached
        """
        print(f"\n=== WAITING FOR CLUSTER TO BECOME HEALTHY (max wait: {max_wait_attempts*retry_interval}s) ===\n")
        
        for attempt in range(1, max_wait_attempts + 1):
            print(f"Health check attempt {attempt}/{max_wait_attempts}...")
            
            if self.perform_all_checks(app_namespace=app_namespace):
                print(f"Cluster health check passed after {attempt} attempts ({attempt*retry_interval}s)")
                return True
                
            # If maximum attempts reached, return failure
            if attempt >= max_wait_attempts:
                print(f"Maximum wait time reached ({max_wait_attempts*retry_interval}s). Cluster is still not healthy.")
                return False
                
            # Wait before retrying
            print(f"Waiting {retry_interval}s before next health check...")
            time.sleep(retry_interval)
            
        # This should not be reached, but just in case
        return False
        
    def restart_deployments(self, app_namespace="image-detection"):
        """Restart all deployments in the specified namespace in parallel."""
        print(f"\n=== RESTART DEPLOYMENTS (NAMESPACE: {app_namespace}) ===\n")
        
        # Get all deployments
        cmd = f"kubectl get deployments -n {app_namespace} -o name"
        print(f"Getting deployments with command: {cmd}")
        
        try:
            exit_status, out, err = self.ssh.run_command(cmd)
            if exit_status != 0:
                print(f"Error getting deployments: {err}")
                return False
            
            deployments = out.strip().split()
            if not deployments:
                print(f"No deployments found in namespace {app_namespace}")
                return True
            
            print(f"Found deployments: {', '.join(deployments)}")
            
            restart_cmd = f"kubectl rollout restart deployment -n {app_namespace}"
            print(f"Restarting ALL deployments in parallel with command: {restart_cmd}")
            exit_status, out, err = self.ssh.run_command(restart_cmd)
            if exit_status != 0:
                print(f"Warning: Failed to restart deployments: {err}")
            else:
                print(f"Successfully triggered parallel restart for all deployments")
            
            print("Waiting for all deployments to complete restart...")
            wait_cmd = f"kubectl rollout status deployment -n {app_namespace} --timeout=300s"
            exit_status, out, err = self.ssh.run_command(wait_cmd)
            if exit_status != 0:
                print(f"Warning: Some deployments may not be fully ready: {err}")
            else:
                print(f"All deployments have successfully rolled out")
            
            print("\nParallel deployment restart completed.")
            
            print("\nVerifying cluster health after restart...")
            return self.perform_all_checks(app_namespace=app_namespace)
            
        except Exception as e:
            print(f"Error during deployment restart: {e}")
            return False