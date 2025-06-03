import os

class K8sController:
    """Handles Kubernetes operations (applying chaos experiments on master)."""

    def __init__(self, ssh_manager):
        self.ssh = ssh_manager
        # Define remote path for uploading the chaos experiment YAML on the master node
        self.remote_yaml_path = "/tmp/chaos_config.yaml"

    def apply_chaos_experiment(self, local_yaml_path):
        """
        Upload the chaos YAML if it exists locally; otherwise assume it's already
        present on the master at the given path. Then apply it via kubectl.
        If it's a shell script, execute it in background instead.
        """
        # Check if it's a shell script
        is_shell_script = local_yaml_path and local_yaml_path.endswith('.sh')

        # Determine whether to upload or use the path directly
        if os.path.isfile(local_yaml_path):
            filename = os.path.basename(local_yaml_path)
            if is_shell_script:
                remote_path = f"/tmp/{filename}"
            else:
                remote_path = self.remote_yaml_path
                
            print(f"Uploading chaos {'script' if is_shell_script else 'experiment YAML'} '{filename}' to remote path '{remote_path}'...")
            try:
                self.ssh.upload_file(local_yaml_path, remote_path)
                print(f"Successfully uploaded '{filename}' to {remote_path}")
            except Exception as e:
                print(f"Failed to upload file '{local_yaml_path}' to '{remote_path}': {e}")
                raise
        else:
            # Local file not found: assume it's already on master at that path
            remote_path = local_yaml_path
            print(f"Local file '{local_yaml_path}' not found; will apply remote path directly")

        # Apply the chaos experiment based on file type
        if is_shell_script:
            # Make script executable
            chmod_cmd = f"chmod +x {remote_path}"
            print(f"Making script executable with command: {chmod_cmd}")
            _, _, _ = self.ssh.run_command(chmod_cmd)
            
            # Execute the shell script in background
            cmd = f"nohup bash {remote_path} > /tmp/chaos_script.log 2>&1 &"
            print(f"Executing chaos script in background: {cmd}")
        else:
            # Apply YAML with kubectl
            cmd = f"kubectl apply -f {remote_path}"
            print(f"Applying chaos experiment via kubectl with command: {cmd}")
            
        try:
            exit_status, out, err = self.ssh.run_command(cmd)
        except Exception as e:
            print(f"Failed to execute command '{cmd}': {e}")
            raise
            
        if exit_status != 0:
            print(f"Command failed (exit status {exit_status}): {err.strip()}")
            raise Exception(f"Failed to apply chaos experiment: {err.strip()}")
            
        print(f"Chaos {'script started in background' if is_shell_script else 'experiment applied successfully'}")

    def delete_chaos_experiment(self, schedule_name):
        cmd = f"kubectl delete schedule {schedule_name} -n chaos-mesh"
        print(f"Deleting chaos schedule '{schedule_name}' via kubectl with command: {cmd}")
        exit_status, out, err = self.ssh.run_command(cmd)
        if exit_status != 0:
            raise Exception(f"Failed to delete chaos experiment: {err.strip()}")
        print(f"Chaos schedule '{schedule_name}' deleted successfully.")