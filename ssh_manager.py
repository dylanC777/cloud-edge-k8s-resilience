import paramiko
import os
import posixpath

class SSHManager:
    """Manages an SSH connection to a remote host using Paramiko."""
    def __init__(self, host, user, key_path):
        self.host = host
        self.user = user
        self.key_path = key_path
        self.client = None

    def connect(self):
        """Establish an SSH connection."""
        print(f"Connecting to {self.host} as {self.user}...")
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            transport_options = {
                'banner_timeout': 200,
                'auth_timeout': 200,
                'timeout': 200
            }

            self.client.connect(
                hostname=self.host, 
                username=self.user, 
                key_filename=self.key_path,
                **transport_options
            )

            transport = self.client.get_transport()
            transport.set_keepalive(15)
            print(f"Connected to {self.host} with keepalive enabled")
        except Exception as e:
            error_msg = f"Failed to connect to {self.host} as {self.user}: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def run_command(self, command):
        """
        Execute a command on the remote host and return (exit_status, stdout, stderr).
        """
        print(f"Executing command on {self.host}: {command}")
        try:
            if not self.client:
                raise Exception("SSH client is not connected.")
            stdin, stdout, stderr = self.client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            print(f"Command executed with exit status {exit_status}")
            return exit_status, out, err
        except Exception as e:
            error_msg = f"Failed to run command '{command}' on {self.host}: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def upload_file(self, local_path, remote_path):
        """Upload a file to the remote host."""
        print(f"Uploading file from {local_path} to {self.host}:{remote_path}")
        sftp = None
        try:
            if not self.client:
                raise Exception("SSH client is not connected.")
            if not os.path.exists(local_path):
                warning_msg = f"Local file {local_path} does not exist."
                print(f"WARNING: {warning_msg}")
                raise Exception(warning_msg)
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            print(f"File uploaded: {local_path} -> {remote_path}")
        except Exception as e:
            error_msg = f"Failed to upload file {local_path} to {remote_path}: {e}"
            print(error_msg)
            raise Exception(error_msg)
        finally:
            if sftp:
                sftp.close()

    def download_file(self, remote_path, local_path):
        """Download a file from the remote host."""
        print(f"Downloading file from {self.host}:{remote_path} to {local_path}")
        sftp = None
        try:
            if not self.client:
                raise Exception("SSH client is not connected.")
            sftp = self.client.open_sftp()
            try:
                sftp.stat(remote_path)
            except Exception:
                error_msg = f"Remote file {remote_path} does not exist."
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
            sftp.get(remote_path, local_path)
            print(f"File downloaded: {remote_path} -> {local_path}")
        except Exception as e:
            error_msg = f"Failed to download file {remote_path} to {local_path}: {e}"
            print(error_msg)
            raise Exception(error_msg)
        finally:
            if sftp:
                sftp.close()

    def upload_dir(self, local_dir, remote_dir):
        """
        Recursively upload all files from local_dir to remote_dir on the remote host.
        Creates any missing subdirectories under remote_dir.
        """
        print(f"Uploading directory {local_dir} to {self.host}:{remote_dir}")
        sftp = None
        try:
            if not self.client:
                raise Exception("SSH client is not connected.")
            sftp = self.client.open_sftp()
            # Check local directory existence
            if not os.path.isdir(local_dir):
                error_msg = f"Local directory {local_dir} does not exist or is not a directory."
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
            # Ensure base remote_dir exists
            try:
                sftp.stat(remote_dir)
            except Exception:
                try:
                    sftp.mkdir(remote_dir)
                    print(f"Created directory: {remote_dir}")
                except Exception as e_mkdir:
                    error_msg = f"Failed to create remote directory {remote_dir}: {e_mkdir}"
                    print(error_msg)
                    raise Exception(error_msg)
            # Walk through local directory
            for root, dirs, files in os.walk(local_dir):
                relative_path = os.path.relpath(root, local_dir)
                remote_root = remote_dir if relative_path == '.' else posixpath.join(remote_dir, relative_path)
                # Ensure current remote directory exists
                try:
                    sftp.stat(remote_root)
                except Exception:
                    try:
                        sftp.mkdir(remote_root)
                        print(f"Created directory: {remote_root}")
                    except Exception as e_mkdir2:
                        error_msg = f"Failed to create remote directory {remote_root}: {e_mkdir2}"
                        print(error_msg)
                        raise Exception(error_msg)
                # Upload all files in this directory
                for filename in files:
                    local_path = os.path.join(root, filename)
                    remote_path = posixpath.join(remote_root, filename)
                    try:
                        sftp.put(local_path, remote_path)
                        print(f"Uploaded file: {local_path} -> {remote_path}")
                    except Exception as e_put:
                        error_msg = f"Failed to upload file {local_path} to {remote_path}: {e_put}"
                        print(error_msg)
                        raise Exception(error_msg)
            print(f"Directory upload complete: {local_dir} to {remote_dir}")
        except Exception as e:
            error_msg = f"Failed to upload directory {local_dir} to {remote_dir}: {e}"
            print(error_msg)
            raise Exception(error_msg)
        finally:
            if sftp:
                sftp.close()

    def close(self):
        """Close the SSH connection."""
        if not self.client:
            print("No SSH connection to close.")
            return
        print("Closing SSH connection.")
        try:
            self.client.close()
            self.client = None
            print("SSH connection closed.")
        except Exception as e:
            error_msg = f"Failed to close SSH connection to {self.host}: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def connect(self):
        """Establish an SSH connection."""
        print(f"Connecting to {self.host} as {self.user}...")
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Connect using the provided host, username, and private key file
            self.client.connect(hostname=self.host, username=self.user, key_filename=self.key_path)
            transport = self.client.get_transport()
            transport.set_keepalive(30)
            print(f"Connected to {self.host} with keepalive enabled")
        except Exception as e:
            error_msg = f"Failed to connect to {self.host} as {self.user}: {e}"
            print(error_msg)
            raise Exception(error_msg)