# Cloud-Edge Kubernetes Resilience Evaluation Framework

This repository provides a modular framework for evaluating the **resilience of Kubernetes-based cloud-edge deployments** through large-scale fault injection experiments. It integrates automated **failure scheduling**, **load generation**, and **metric collection** for end-to-end system assessment.

---

## 🔍 Overview

Cloud-edge architectures face heightened fault sensitivity due to distributed topologies and constrained edge resources. This framework enables reproducible resilience testing under:

- Varying **cluster sizes** (4-node, 8-node)
- Different **application architectures** (monolithic vs. microservices)
- Diverse **fault types** (e.g., pod kill, CPU stress, network delay)
- Multiple **deployment modes** (cloud vs. edge)
- Configurable **load patterns** (constant, concurrent, piggyback)

> 🧪 A total of **12,000+ experiments** were conducted, producing over **57 million request-level records** and **30 GB of logs**.

---

## 🧩 Components

| Module              | Description                                           |
|---------------------|-------------------------------------------------------|
| `main.py`           | Orchestrates the full test cycle                      |
| `ssh_manager.py`    | Handles remote control of Kubernetes/client nodes     |
| `k8s_controller.py` | Applies Chaos Mesh YAML files to inject faults        |
| `locust_runner.py`  | Triggers remote Locust load tests                     |
| `result_manager.py` | Saves logs, CSVs, and per-test summaries              |
| `check_cluster.py`  | Validates cluster readiness before experiments        |
| `config.yaml`       | Stores system paths, credentials, and test parameters |

---

## 🚀 Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
