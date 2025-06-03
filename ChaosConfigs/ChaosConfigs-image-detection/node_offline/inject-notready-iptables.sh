#!/bin/bash

# === 必填配置 ===
WORKER_IP="118.138.243.212"              # 你的 worker1 IP
SSH_USER="ubuntu"
SSH_KEY="/home/ubuntu/.ssh/FIT-5225"
K8S_API_SERVER="118.138.241.185"         # Master 的 API Server 地址
DURATION=60                              # 模拟 NotReady 的秒数
NODE_NAME="zihaochen-mscminorthesis-worker1"

# === 注入故障 ===
echo "🚨 Injecting failure: Blocking access to K8s API Server from worker node..."
ssh -i "$SSH_KEY" ${SSH_USER}@${WORKER_IP} \
  "sudo iptables -A OUTPUT -p tcp -d $K8S_API_SERVER --dport 6443 -j DROP"

echo "⏳ Waiting $DURATION seconds while node becomes NotReady..."
sleep $DURATION

# === 恢复连接 ===
echo "✅ Recovering: Unblocking API Server access..."
ssh -i "$SSH_KEY" ${SSH_USER}@${WORKER_IP} \
  "sudo iptables -D OUTPUT -p tcp -d $K8S_API_SERVER --dport 6443 -j DROP"

echo "⌛ Waiting 15 seconds for node to reconnect..."
sleep 15

echo "🔄 Running 'kubectl uncordon $NODE_NAME' to restore scheduling..."
kubectl uncordon $NODE_NAME

echo "✅ Done! Final node status:"
kubectl get nodes
