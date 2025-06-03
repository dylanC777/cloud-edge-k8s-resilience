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

## ⚙️ Minimal Dependencies

```txt
paramiko — for SSH automation  
pyyaml   — for config and YAML parsing
```

Install all dependencies:

```bash
pip install -r requirements.txt
```

---

## 🧪 Setup Kubernetes & Client Nodes

1. **Kubernetes Master Node**  
   Ensure [Chaos Mesh](https://chaos-mesh.org) is installed and running.

2. **Client Node**  
   A separate node should run Locust to generate traffic.

3. **Configuration**  
   All system paths, IP addresses, namespaces, and credentials are set in:

```yaml
config.yaml
```

---

## ▶️ Run a Test

```bash
python main.py --config config.yaml
```

Test artifacts will be saved under the `results/` directory, including:

- ✅ Locust log CSV  
- ✅ Console output  
- ✅ Copy of the fault YAML used  
- ✅ Per-test summary report

---

## 📁 File Structure

```text
.
├── main.py
├── ssh_manager.py
├── k8s_controller.py
├── locust_runner.py
├── result_manager.py
├── check_cluster.py
├── cluster_checker.py
├── csv_processor.py
├── config.yaml
├── requirements.txt
└── results/             # generated automatically
```

---

## 📂 Dataset Access

The dataset generated using this framework includes:

- ~12,000 fault injection test runs  
- ~57 million per-request records  
- ~30 GB of structured time-series logs

> 🔒 **Currently stored in a private repository** during the thesis review period.  
> 🎓 **Interested researchers** may contact the author for early access.  
> 📢 Dataset and framework will be **publicly released** after thesis publication.

---

## 📄 License

To be confirmed. The code will be released under an open-source license (e.g., MIT or Apache 2.0) following thesis submission.

---

## 📬 Citation

If this framework supports your research, please cite the associated thesis or [contact the author](mailto:zihao.chen@monash.edu) for preliminary citation format.

---

## 📫 Contact

**Zihao Chen**  
Monash University  
✉️ zihao.chen@monash.edu  
🌐 [GitHub Repository](https://github.com/dylanC777/cloud-edge-k8s-resilience)
