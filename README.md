# Dos-attack
# 🧪 Powerful HTTP Load Testing Tool

This is a powerful Python-based HTTPS load testing and DoS simulation tool. It supports multiple modes including **Load Test**, **GoldenEye**, and **Slowloris**, with proxy and debug options for testing flexibility.

---

## ⚙️ Features

- Load testing with configurable request count, workers, and timeout
- GoldenEye-style socket-based stress testing
- Slowloris-style attack with optional proxy and user-agent rotation
- Optional debug logging for request traceability

---

## 🚀 How to Run

### 1. 📦 Install Dependencies

#### Option A: Using Virtual Environment (Recommended)

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install requests
pip install PySocks  # Only if using proxy with Slowloris mode
