#!/usr/bin/env python3
import yaml
import os
import sys
import argparse
from ssh_manager import SSHManager
from cluster_checker import ClusterChecker

def main():
    parser = argparse.ArgumentParser(description='Check Kubernetes cluster health before experiments')
    parser.add_argument('--config', type=str, default='config.yaml', 
                        help='Path to configuration file (default: config.yaml)')
    parser.add_argument('--namespace', type=str,
                        help='Application namespace to check (overrides config)')
    args = parser.parse_args()

    # Load configuration from config file
    config_path = args.config
    if not os.path.isfile(config_path):
        config_path = os.path.join(os.path.dirname(__file__), args.config)
        if not os.path.isfile(config_path):
            print(f"Error: Configuration file not found at {args.config}")
            sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Get master configuration
    master_cfg = config.get('master', {})
    if not master_cfg.get('host') or not master_cfg.get('user') or not master_cfg.get('key_path'):
        print("Error: Master node configuration incomplete in config.yaml")
        sys.exit(1)
        
    # Get application namespace (command line overrides config)
    app_namespace = args.namespace or config.get('app_namespace', 'image-detection')
    
    # Initialize SSH connection to master
    ssh_master = SSHManager(master_cfg.get('host'), master_cfg.get('user'), master_cfg.get('key_path'))
    
    try:
        ssh_master.connect()
        print(f"SSH connection established to master node at {master_cfg.get('host')}")
        
        # Initialize and run cluster checks
        checker = ClusterChecker(ssh_master)
        checks_passed = checker.perform_all_checks(app_namespace=app_namespace)
        
        # Exit with appropriate status code
        if checks_passed:
            print("\nSUCCESS: All cluster health checks passed.")
            sys.exit(0)
        else:
            print("\nWARNING: Some cluster health checks failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if ssh_master.client:
            ssh_master.close()

if __name__ == "__main__":
    main()