#!/bin/bash

# Default settings
RUN_DURATION=120    # Run for 5 minutes (300 seconds) by default
FAILURE_DURATION=30

# Parse command line arguments
while getopts "t:d:" opt; do
  case $opt in
    t) RUN_DURATION=$OPTARG ;;  # -t for total runtime in seconds
    d) FAILURE_DURATION=$OPTARG ;;
    *) echo "Usage: $0 [-t run_duration_seconds] [-d failure_duration]" && exit 1 ;;
  esac
done

# Record start time
START_TIME=$(date +%s)
END_TIME=$((START_TIME + RUN_DURATION))

# Target worker node names
WORKER_NODE_1="zihaochen-mscminorthesis-worker1"
WORKER_NODE_2="zihaochen-mscminorthesis-worker2"
WORKER_NODE_3="zihaochen-mscminorthesis-worker3"

# Set up trap for Ctrl+C and other termination signals
cleanup() {
  echo "Script interrupted. Performing cleanup..."
  
  # Make sure all nodes are uncordoned and kubelet is running
  echo "Making sure all worker nodes are uncordoned and kubelet is running..."
  for node in "$WORKER_NODE_1" "$WORKER_NODE_2" "$WORKER_NODE_3"; do
    kubectl uncordon $node 2>/dev/null
    ssh ubuntu@$node "sudo systemctl start kubelet" 2>/dev/null
  done
  
  echo "Cleanup completed."
  exit 1
}

# Define a final cleanup function that doesn't exit
final_cleanup() {
  echo "Performing final cleanup..."
  
  # Make sure all nodes are uncordoned and kubelet is running
  echo "Making sure all worker nodes are uncordoned and kubelet is running..."
  for node in "$WORKER_NODE_1" "$WORKER_NODE_2" "$WORKER_NODE_3"; do
    kubectl uncordon $node 2>/dev/null
    ssh ubuntu@$node "sudo systemctl start kubelet" 2>/dev/null
  done
  
  echo "Final cleanup completed."
}

trap cleanup SIGINT SIGTERM

# Failure injection function
inject_failure() {
  local cycle_num=$1
  
  echo "===== Failure Injection Cycle $cycle_num ($(date '+%H:%M:%S')) ====="
  
  # Check if we've exceeded our runtime
  CURRENT_TIME=$(date +%s)
  TIME_ELAPSED=$((CURRENT_TIME - START_TIME))
  TIME_REMAINING=$((END_TIME - CURRENT_TIME))
  
  if [ $TIME_REMAINING -le 0 ]; then
    echo "Time limit reached. Stopping failure injection."
    return 1
  fi

  echo "Time elapsed: $TIME_ELAPSED seconds. Time remaining: $TIME_REMAINING seconds"
  
  echo "Injecting failure: Stopping kubelet on all three workers..."
  kubectl drain $WORKER_NODE_1 --ignore-daemonsets --delete-emptydir-data --force
  kubectl drain $WORKER_NODE_2 --ignore-daemonsets --delete-emptydir-data --force
  kubectl drain $WORKER_NODE_3 --ignore-daemonsets --delete-emptydir-data --force
  
  echo "Disabling kubelet service on all three workers..."
  ssh ubuntu@$WORKER_NODE_1 "sudo systemctl stop kubelet"
  ssh ubuntu@$WORKER_NODE_2 "sudo systemctl stop kubelet"
  ssh ubuntu@$WORKER_NODE_3 "sudo systemctl stop kubelet"
  
  echo "All three worker nodes are now in NotReady state."
  
  # Calculate how long to sleep - don't exceed our end time
  CURRENT_TIME=$(date +%s)
  TIME_REMAINING=$((END_TIME - CURRENT_TIME))
  SLEEP_TIME=$FAILURE_DURATION
  
  if [ $TIME_REMAINING -lt $FAILURE_DURATION ]; then
    SLEEP_TIME=$TIME_REMAINING
  fi
  
  if [ $SLEEP_TIME -gt 0 ]; then
    echo "Waiting for $SLEEP_TIME seconds before recovery..."
    sleep $SLEEP_TIME
  else
    echo "No time left for failure duration, proceeding to recovery immediately."
  fi
  
  echo "Recovering Worker Node $WORKER_NODE_1..."
  ssh ubuntu@$WORKER_NODE_1 "sudo systemctl start kubelet"
  kubectl uncordon $WORKER_NODE_1
  
  echo "Recovering Worker Node $WORKER_NODE_2..."
  ssh ubuntu@$WORKER_NODE_2 "sudo systemctl start kubelet"
  kubectl uncordon $WORKER_NODE_2
  
  echo "Recovering Worker Node $WORKER_NODE_3..."
  ssh ubuntu@$WORKER_NODE_3 "sudo systemctl start kubelet"
  kubectl uncordon $WORKER_NODE_3
  
  echo "All worker nodes are now being recovered."
  
  # Add a short delay to allow nodes to fully rejoin the cluster
  echo "Waiting for nodes to rejoin cluster..."
  sleep 5
  
  # Return success if we should continue
  CURRENT_TIME=$(date +%s)
  [ $CURRENT_TIME -lt $END_TIME ]
  return $?
}

# Main loop - run until time expires
cycle_count=0
while true; do
  cycle_count=$((cycle_count + 1))
  
  # inject_failure returns 0 if we should continue, 1 if we should stop
  if ! inject_failure $cycle_count; then
    break
  fi
  
  # Check if we have enough time for another cycle
  CURRENT_TIME=$(date +%s)
  TIME_REMAINING=$((END_TIME - CURRENT_TIME))
  
  echo "Completed cycle $cycle_count. Time remaining: $TIME_REMAINING seconds."
  
  if [ $TIME_REMAINING -lt 15 ]; then  # Conservative estimate for minimum cycle time
    echo "Not enough time remaining for another complete cycle. Ending script."
    break
  fi
done

# Calculate total runtime
FINISH_TIME=$(date +%s)
TOTAL_RUNTIME=$((FINISH_TIME - START_TIME))
MINUTES=$((TOTAL_RUNTIME / 60))
SECONDS=$((TOTAL_RUNTIME % 60))

echo "All failure injection cycles completed."
echo "Script ran for $MINUTES minutes and $SECONDS seconds."
echo "Executed $cycle_count cycles in total."

# Call final cleanup to ensure all nodes are restored
final_cleanup