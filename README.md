# EraseVerify-AI: Ghost Data Still Exists
### HackerRank Orchestrate (October 2026) — Autonomous Personal Data Deletion Audit Agent

[![Tests: Passing (27/27)](https://img.shields.io/badge/Tests-27%2F27%20Passed-brightgreen.svg)](#test-suite-and-validation)
[![Status Accuracy: 100%](https://img.shields.io/badge/Status%20Accuracy-100%25%20(32%2F32)-blue.svg)](#evaluation-and-benchmark-results)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#environment-setup)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey.svg)](#license)

**EraseVerify-AI** is an AI-powered deletion-audit engine designed for complex enterprise architectures. In modern platforms, automated deletion workflows often report **Complete** while personal data secretly persists in read replicas, unpartitioned backups, support attachments, export archives, or distributed logs. Furthermore, active database synchronization connectors and unblocked restore jobs frequently recreate previously deleted data ("ghost data").

EraseVerify-AI resolves the subject's full identity history, extracts and correlates evidence across six heterogeneous data formats, enforces temporal audit boundaries (`captured_at <= audit_at`), executes dynamic policy checks from `deletion_rules.csv`, and produces topologically ordered remediation and verification plans.

---

## Architecture & End-to-End Workflow

The following flowchart illustrates the complete multi-stage pipeline from input request to verified output:

```mermaid
flowchart TD
    A["Input Case<br/>(case_id, email, requested_at, audit_at, request_text)"] --> B{"Stage 1: Authorization<br/>(request_classifier.py)"}
    
    B -->|"Not a Deletion Request<br/>(Export / Access / Opt-Out)"| C["NOT_APPLICABLE<br/>steps_json = []"]
    
    B -->|"Authorized Deletion"| D["Stage 2: Identity Resolution<br/>(identity_resolver.py)"]
    
    D -->|"Resolve Current & Historical IDs<br/>(user_identities.csv + user_audit_log.csv)"| E["Resolved Identity Profile<br/>(user_id, names, current/past emails, phone, hashes)"]
    
    E --> F["Stage 3: Evidence Ingestion & Temporal Gating<br/>(evidence_loader.py & evidence_extractors/)"]
    
    subgraph Evidence Sources ["Evidence Sources (filtered by captured_at <= audit_at)"]
        F1[("SQL Snapshots<br/>(Primary, Replicas, Failovers)")]
        F2["Structured JSON<br/>(Exports, Snapshots, Bundles)"]
        F3["Service Logs<br/>(Trace Correlation & Events)"]
        F4["Handover Texts<br/>(Pipe-delimited Statuses)"]
        F5["PDF Documents<br/>(Tickets, Registers, Handouts)"]
        F6["Console Screenshots<br/>(Admin & Audit Screens)"]
    end
    
    F --> Evidence Sources
    Evidence Sources --> G["Stage 4: Fact Aggregation<br/>(fact_aggregator.py)"]
    
    G -->|"Consolidated Grounded Facts<br/>(Multi-source consensus & trace linking)"| H["Stage 5: Policy Evaluation Engine<br/>(policy_engine.py)"]
    
    I[("Deletion Rules<br/>(deletion_rules.csv)")] --> H
    
    H -->|"Evaluate Treatments<br/>(DELETE, REDACT, ANONYMIZE, RETAIN, TOMBSTONE)"| J{"Are all records compliant<br/>and flows/restores safe?"}
    
    J -->|"Yes (Fully Compliant)"| K["Status: COMPLETE<br/>Generate Evidence-Backed Verifications"]
    J -->|"No (Residual Data / Sync / Restore Risk)"| L["Status: INCOMPLETE<br/>Generate Findings + Remediation + Verifications"]
    
    K --> M["Stage 6: Step Builder & Topological Planner<br/>(step_builder.py)"]
    L --> M
    
    M --> N["Strict Phase Ordering:<br/>1. FINDINGS (with evidence_id)<br/>2. REMEDIATION (Flows -> Restores -> Records)<br/>3. VERIFICATION (Future post-checks)"]
    
    N --> O["Final Output Serialization<br/>output.csv (case_id, deletion_status, steps_json)"]
```

---

## Key Features & Engineering Highlights

1. **Deterministic & High-Throughput Engine:**
   - Evaluates all **518 evaluation cases in ~77 seconds** (~6.7 cases/sec) with zero operational latency and zero LLM cloud inference cost.
2. **Multi-Line Distributed Trace Correlation:**
   - Distributed query logs (e.g. `service_events_ap_south_20260915.log`) decouple user lookup events (`trace_id` + `email`) from completion events (`trace_id` + `resource_id`). EraseVerify-AI performs multi-line trace linking to uncover residual data and ghost restore jobs.
3. **Temporal Authority Enforcement (`<= audit_at`):**
   - Strictly ignores evidence created after the case's `audit_at` timestamp. Prevents future state leakage when multiple snapshot bundles exist (e.g., favoring `evidence_92` over future `evidence_02`).
4. **Historical Identity Resolution:**
   - Maps requests submitted under historical emails back to the master `user_id`, uncovering unredacted tombstones, legacy logs, and secondary replicas.
5. **Account Tombstone & Retention Safety:**
   - Preserves policy-mandated audit logs (e.g., `security_service` audit trails required for 365 days) and account tombstones while ensuring direct PII (`name`, `email`, `phone`, `email_hash`) is properly redacted.
6. **Topologically Ordered Remediation Planning:**
   - Generates executable remediation sequences: active replication pipelines and restore queues are stopped first (`DISABLE_DATA_FLOW`, `BLOCK_RESTORE`), followed by record deletion or redaction (`DELETE_RECORD`, `REDACT_RECORD`), and finalized with post-remediation verification checks.

---

## Directory Structure

```text
EraseVerify-AI/
├── README.md                           # Master project documentation
├── AGENTS.md                           # Challenge & coding agent contract
├── problem_statement.md                # Official challenge specification
├── requirements.txt                    # Python dependencies
├── log.txt                             # AGENTS.md audit log (chat transcript)
├── output.csv                          # Final generated predictions (518 cases)
├── code.zip                            # Clean submission ZIP package
├── code/
│   ├── main.py                         # End-to-end CLI & pipeline orchestrator
│   ├── config.py                       # Cross-platform paths and constants
│   ├── request_classifier.py           # Multilingual deletion request classifier
│   ├── identity_resolver.py            # Current & historical identity resolver
│   ├── evidence_loader.py              # Temporal evidence manifest filter
│   ├── fact_aggregator.py              # Multi-source fact consensus & trace linker
│   ├── policy_engine.py                # Dynamic rule matcher (deletion_rules.csv)
│   ├── step_builder.py                 # Schema validator & topological step sorter
│   ├── evidence_extractors/            # Modular format-specific extractors
│   │   ├── sql_extractor.py            # SQLite & SQL dump parser
│   │   ├── json_extractor.py           # Snapshot & export parser
│   │   ├── log_extractor.py            # Distributed trace log parser
│   │   ├── text_extractor.py           # Pipe-delimited handover parser
│   │   ├── pdf_extractor.py            # Compliance PDF document parser
│   │   └── image_extractor.py          # Screenshot & console parser
│   └── evaluation/
│       ├── evaluator.py                # Public benchmark evaluator
│       ├── main.py                     # Evaluation CLI runner
│       ├── evaluation_report.md        # Stage 5 evaluation report
│       └── usage_report.md             # Stage 6 full-run usage report
├── dataset/                            # Evaluation datasets & evidence corpus
│   ├── deletion_requests.csv           # 518 evaluation cases
│   ├── sample_deletion_requests.csv    # 32 public sample cases
│   ├── sample_output.csv               # Gold reference for public samples
│   ├── user_identities.csv             # Current user identity snapshots
│   ├── user_audit_log.csv              # Historical identity change logs
│   ├── system_activity.csv             # Global system activity stream
│   ├── deletion_rules.csv              # Deletion & retention policy rules
│   ├── evidence_files.csv              # Evidence metadata manifest
│   └── evidence/                       # Evidence files (sql, json, log, txt, pdf, png)
├── evaluation/                         # Top-level submission reports mirror
│   ├── evaluation_report.md            # Comprehensive benchmark report
│   └── usage_report.md                 # Full-dataset usage & token report
├── scratch/
│   └── validate_output.py              # Comprehensive schema & step validator
└── tests/
    ├── test_stage2.py                  # Identity & classifier unit tests
    ├── test_stage3_extractors.py       # Evidence extractor integration tests
    ├── test_stage4_policy_and_steps.py # Policy engine & step builder tests
    └── test_synthetic_edge_cases.py    # 3 custom synthetic edge-case tests
```

---

## Environment Setup

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.10, 3.11, 3.12, 3.14)
- **Git** (for version tracking)
- **PowerShell** (Windows) or **Bash** (macOS/Linux)

### 2. Installation
Clone the repository and install the minimal dependencies:

```bash
# Clone repository
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd EraseVerify-AI

# Install dependencies
pip install -r requirements.txt
```

*Key dependencies:* `pytest`, `pdfplumber`, `pandas`.

---

## Instructions & Usage Guide

### 1. Generate Final Predictions on the Full Dataset (518 Cases)
Run the pipeline orchestrator to process all 518 cases from `dataset/deletion_requests.csv` and generate `output.csv` at the repository root:

```bash
python code/main.py
```

*Optional custom paths:*
```bash
python code/main.py --input dataset/sample_deletion_requests.csv --output scratch/sample_output.csv
```

### 2. Run the Benchmark Evaluator Against Public Samples
Evaluate the engine against all 32 public ground-truth cases:

```bash
python code/evaluation/evaluator.py
```

### 3. Run the Automated Test Suite
Run all 27 unit, integration, and synthetic edge-case tests:

```bash
pytest
```

### 4. Validate `output.csv` Schema and Step Integrity
Run the automated validation tool to ensure exact schema compliance, row count, sorting, phase ordering, and evidence citation rules:

```bash
python scratch/validate_output.py
```

---

## Deletion Policy & Step Schema Specifications

### 1. Output Format (`output.csv`)
The output CSV must contain exactly three columns in this order:
```text
case_id,deletion_status,steps_json
```

- `case_id`: The unique case identifier (e.g. `case_33`).
- `deletion_status`: Must be one of `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `steps_json`: An ordered JSON array of step objects (or `[]` if `NOT_APPLICABLE`).

### 2. Step Object Schema
```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_54"
}
```

### 3. Allowed Operations & State Matrix

| Phase | Operation | State | Meaning | Evidence ID Rule |
|---|---|---|---|---|
| **FINDING** | `REPORT_REMAINING_RECORD` | `PRESENT` | Prohibited record still exists | Cites participant-visible evidence ID |
| **FINDING** | `REPORT_EXPOSED_PII` | `PRESENT` | Retained record exposes unredacted PII | Cites participant-visible evidence ID |
| **FINDING** | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` | Active connector/pipeline recreates data | Cites participant-visible evidence ID |
| **FINDING** | `REPORT_RESTORE_RISK` | `ACTIVE` | Backup queue will restore deleted data | Cites participant-visible evidence ID |
| **REMEDIATION** | `DISABLE_DATA_FLOW` | `DISABLED` | Stop active data flow / sync pipeline | Empty string (`""`) |
| **REMEDIATION** | `BLOCK_RESTORE` | `BLOCKED` | Prevent restore of user's records | Empty string (`""`) |
| **REMEDIATION** | `DELETE_RECORD` | `ABSENT` | Delete the record | Empty string (`""`) |
| **REMEDIATION** | `REDACT_RECORD` | `REDACTED` | Remove direct identifying fields | Empty string (`""`) |
| **REMEDIATION** | `ANONYMIZE_RECORD` | `ANONYMIZED` | Irreversibly unlink record from user | Empty string (`""`) |
| **VERIFICATION** | `VERIFY_RECORD_ABSENT` | `ABSENT` | Confirm record no longer exists | Cites evidence if `COMPLETE`; empty `""` if future |
| **VERIFICATION** | `VERIFY_RECORD_PRESENT` | `PRESENT` | Confirm retained record is preserved | Cites evidence if `COMPLETE`; empty `""` if future |
| **VERIFICATION** | `VERIFY_RECORD_REDACTED` | `REDACTED` | Confirm required fields are redacted | Cites evidence if `COMPLETE`; empty `""` if future |
| **VERIFICATION** | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | Confirm record is anonymized | Cites evidence if `COMPLETE`; empty `""` if future |
| **VERIFICATION** | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` | Confirm data flow is inactive | Cites evidence if `COMPLETE`; empty `""` if future |
| **VERIFICATION** | `VERIFY_RESTORE_BLOCKED` | `BLOCKED` | Confirm restore path is blocked | Cites evidence if `COMPLETE`; empty `""` if future |

---

## Evaluation and Benchmark Results

### 1. Public Sample Evaluation (32 Cases)
Execution of `python code/evaluation/evaluator.py` against `dataset/sample_output.csv`:

```text
============================================================
     GHOST DATA STILL EXISTS — EVALUATION REPORT
============================================================
Total Evaluated Cases:     32
Valid JSON Serialization:  32 / 32 (100.0%)
Schema Compliance:         32 / 32 (100.0%)
------------------------------------------------------------
Case Status Accuracy:      32 / 32 (100.0%)
Exact Sequence Accuracy:   13 / 32 (40.6%)
Step Count Match Cases:    53.1%
Overall Step Field Acc:    88.2%
------------------------------------------------------------
Field-Level Accuracies:
  - phase          : 97.1%
  - system_id      : 86.7%
  - resource_id    : 79.2%
  - operation      : 85.0%
  - state          : 86.1%
  - evidence_id    : 94.8%
============================================================
```

### 2. Synthetic Edge-Case Tests (`tests/test_synthetic_edge_cases.py`)
1. **`SYNTH_001` (Multilingual Data Portability Request):**
   - User submits GDPR Article 20 data export request in Spanish.
   - Result: Correctly classified as `NOT_APPLICABLE` with `steps_json = []`. (**PASSED**)
2. **`SYNTH_002` (Historical Alias Drift & Tombstone Violation):**
   - User changed email. Primary account tombstoned, but secondary replica retains old email.
   - Result: Discovers unredacted PII, issues `REDACT_RECORD` and verifies post-remediation state. (**PASSED**)
3. **`SYNTH_003` (Ghost Data Active Restore Risk):**
   - Primary database row absent, but active backup restore process would restore data.
   - Result: Emits `REPORT_RESTORE_RISK`, generates `BLOCK_RESTORE` remediation, and verifies blocked state. (**PASSED**)

---

## Packaging & Submission Instructions

### Submission Artifacts Checklist
1. **`output.csv`:** Place at the repository root. Contains 518 data rows sorted by `case_id`.
2. **`code.zip`:** Clean ZIP package containing `code/`, `README.md`, and `evaluation/` reports.
3. **`chat_transcript`:** The root [`log.txt`](./log.txt) file recording all agent interaction turns.
4. **AI Interview:** Technical defense of architecture, trace correlation, and policy rules.

### How to Package `code.zip`

**macOS / Linux:**
```bash
zip -r code.zip README.md code evaluation -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**
```powershell
Get-ChildItem -Path "code" -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Compress-Archive -Path README.md, code, evaluation -DestinationPath code.zip -Force
```

### Official Challenge & Submission Link
Submissions must be submitted directly to the official HackerRank Orchestrate challenge portal:

🔗 **[https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists](https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)**

---

## License

This project is licensed under the MIT License. Developed for the HackerRank Orchestrate (October 2026) Challenge.
