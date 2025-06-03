#!/bin/bash

# Default settings
RUN_DURATION=120    # Run for 2 minutes (120 seconds) by default
FAILURE_DURATION=1  # How long each failure lasts (seconds)

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

# Target Worker node names
WORKER_NODES=(
  "zihaochen-mscminorthesis-worker1"
  "zihaochen-mscminorthesis-worker2"
  "zihaochen-mscminorthesis-worker3"
)

# Set up trap for Ctrl+C and other termination signals
cleanup() {
  echo "Script interrupted. Performing cleanup..."
  
  # Try to uncordon all nodes to ensure they're left in a good state
  for node in "${WORKER_NODES[@]}"; do
    echo "Making sure $node is uncordoned and kubelet is running..."
    kubectl uncordon $node 2>/dev/null
    ssh ubuntu@$node "sudo systemctl start kubelet" 2>/dev/null
  done
  
  echo "Cleanup completed."
  exit 1
}

# Define a final cleanup function that doesn't exit
final_cleanup() {
  echo "Performing final cleanup..."
  
  # Try to uncordon all nodes to ensure they're left in a good state
  for node in "${WORKER_NODES[@]}"; do
    echo "Making sure $node is uncordoned and kubelet is running..."
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
  TIME_REMAINING=$((END_TIME - CURRENT_TIME))
  
  if [ $TIME_REMAINING -le 0 ]; then
    echo "Time limit reached. Stopping failure injection."
    return 1
  fi

  echo "Time remaining: $TIME_REMAINING seconds"
  
  # Randomly select two nodes
  # Create array of indices 0,1,2 and shuffle
  indexes=(0 1 2)
  # Fisher-Yates shuffle algorithm
  for i in {2..0}; do
    j=$(($RANDOM % ($i+1)))
    temp=${indexes[$i]}
    indexes[$i]=${indexes[$j]}
    indexes[$j]=$temp
  done
  
  # Select the first two indices corresponding to nodes
  SELECTED_NODE_1=${WORKER_NODES[${indexes[0]}]}
  SELECTED_NODE_2=${WORKER_NODES[${indexes[1]}]}
  
  echo "Randomly selected nodes for this cycle: $SELECTED_NODE_1 and $SELECTED_NODE_2"
  
  echo "Injecting failure: Stopping kubelet on $SELECTED_NODE_1 and $SELECTED_NODE_2..."
  kubectl drain $SELECTED_NODE_1 --ignore-daemonsets --delete-emptydir-data --force
  kubectl drain $SELECTED_NODE_2 --ignore-daemonsets --delete-emptydir-data --force
  
  echo "Disabling kubelet service on both workers..."
  ssh ubuntu@$SELECTED_NODE_1 "sudo systemctl stop kubelet"
  ssh ubuntu@$SELECTED_NODE_2 "sudo systemctl stop kubelet"
  
  echo "Nodes $SELECTED_NODE_1 and $SELECTED_NODE_2 are now in NotReady state."
  
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
  
  echo "Recovering Node $SELECTED_NODE_1..."
  ssh ubuntu@$SELECTED_NODE_1 "sudo systemctl start kubelet"
  kubectl uncordon $SELECTED_NODE_1
  
  echo "Recovering Node $SELECTED_NODE_2..."
  ssh ubuntu@$SELECTED_NODE_2 "sudo systemctl start kubelet"
  kubectl uncordon $SELECTED_NODE_2
  
  echo "Nodes $SELECTED_NODE_1 and $SELECTED_NODE_2 are now Ready again."
  
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

# Call the final cleanup function to ensure all nodes are restored
final_cleanup