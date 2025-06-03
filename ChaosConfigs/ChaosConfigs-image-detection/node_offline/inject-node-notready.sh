#!/bin/bash

# 目标 Worker 节点名称
WORKER_NODE="zihaochen-mscminorthesis-cluster2-worker1"

echo "Injecting failure: Stopping kubelet on Worker $WORKER_NODE..."
kubectl drain $WORKER_NODE --ignore-daemonsets --delete-emptydir-data --force

echo "Disabling kubelet service..."
ssh ubuntu@$WORKER_NODE "sudo systemctl stop kubelet"

echo "Worker $WORKER_NODE is now in NotReady state."
echo "Waiting for 1 minute before recovering..."
sleep 60  # 等待 60 秒

echo "Recovering Worker Node $WORKER_NODE..."
ssh ubuntu@$WORKER_NODE "sudo systemctl start kubelet"
kubectl uncordon $WORKER_NODE

echo "Worker $WORKER_NODE is now Ready again."

