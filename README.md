# Autonomous AI Self-Healing CI/CD Pipeline

An automated CI/CD pipeline that detects code style violations and package security vulnerabilities, generates fixes using Google Gemini, and opens an autonomous Pull Request with the remediated patch.

---

## Workflow Diagram

```text
[ Developer Push / Pull Request ]
               │
               ▼
   [ GitHub Actions Runner ]
     ├── 1. Code Quality Scan (flake8)       ──> linter_errors.log
     └── 2. Security CVE Scan (pip-audit)    ──> cve_errors.log
               │
               ▼
  [ AI Remediation Engine (heal.py) ]
     ├── Concurrent Processing (ThreadPoolExecutor)
     ├── Dynamic Reasoning Budget (Adaptive Thinking Config)
     ├── Retry & Model Fallback (gemini-3.6-flash / gemini-2.5-flash)
     └── Direct Code & Dependency Patching
               │
               ▼
[ Autonomous Pull Request Created ]
  └── Generates 'auto-heal/ci-patch' branch for maintainer review
```

---

## Core Features

* **Dual Remediation Workers**: Fixes PEP 8 code violations in `main.py` and patches CVE vulnerabilities in `requirements.txt` concurrently.
* **Adaptive Thinking**: Dynamically switches reasoning budgets based on error severity and log complexity.
* **Resilient Fallback**: Automatically catches API rate spikes and reroutes requests across available model tiers.
* **Zero Manual Effort**: Scans, heals, and opens an actionable GitHub Pull Request without manual developer intervention.

---

## Project Structure

* **`heal.py`**: The core AI remediation script powered by the `google-genai` SDK.
* **`.github/workflows/ci.yml`**: GitHub Actions orchestration file managing CI runs, scan logs, and automated PR generation.
* **`main.py`**: Application source file analyzed by the pipeline.
* **`requirements.txt`**: Project dependency manifest scanned for security CVEs.

---

## Local Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Shailesh694/self-healing-demo.git](https://github.com/Shailesh694/self-healing-demo.git)
   cd self-healing-demo
   ```

2. **Install dependencies:**
   ```bash
   pip install flake8 pip-audit google-genai
   pip install -r requirements.txt
   ```

3. **Set the Gemini API Key:**
   * **PowerShell:**
     ```powershell
     $env:GEMINI_API_KEY="your-gemini-api-key"
     ```
   * **Bash / Linux:**
     ```bash
     export GEMINI_API_KEY="your-gemini-api-key"
     ```

4. **Run manual healing locally:**
   ```bash
   python heal.py
   ```