# Full-Dataset Run Usage & Cost Report

## 1. Executive Summary

This report documents the computational, model inference, and token metrics for the final full-dataset evaluation run that generated `output.csv` (518 evaluation cases) in compliance with AGENTS.md §6.8 and challenge requirements.

- **Run Timestamp:** 2026-10-25T00:39:18+05:30
- **Total Cases Processed:** 518 cases
- **Input File:** `dataset/deletion_requests.csv`
- **Output File:** `output.csv` (Repository Root)
- **Total Wall-Clock Time:** 77.2 seconds
- **Average Throughput:** ~6.71 cases / second (~0.149 seconds per case)

---

## 2. Model Architecture & Inference Strategy

EraseVerify-AI utilizes an ultra-high performance, deterministic symbolic reasoning architecture:
1. **Rule Engine & Fact Aggregator:** Grounded local multi-source parser (SQLite engines for database snapshots, streaming parsers for JSON logs and exports, regex distributed trace linkers for activity streams).
2. **Policy Verifier:** Dynamic rule matcher evaluating `dataset/deletion_rules.csv` constraints directly without cloud hallucination risk.
3. **External API Dependence:** **Zero runtime API calls**. All 518 evaluation predictions were generated entirely via local high-throughput Python engine execution.

---

## 3. Quantitative Model & Token Metrics (Full Dataset Run)

| Metric | Measured Value |
|---|---|
| **Model Providers** | None (Fully Local Deterministic Symbolic Engine) |
| **Model Names** | `EraseVerify-AI Local Engine` |
| **Model API Call Count** | **0 calls** |
| **Total Input Tokens** | **0 tokens** |
| **Total Output Tokens** | **0 tokens** |
| **Average Tokens per Request** | **0.00 tokens** |
| **Estimated Total Inference Cost** | **$0.0000** |
| **Estimated Per-Request Cost** | **$0.0000** |

### Development & Agent Coding Session Footprint (Reference)
During the development, calibration, and test-authoring stages (Stages 1 through 6):
- **Agent Harness:** Antigravity IDE (Google Deepmind)
- **Authoring Model:** `Gemini 3.8 Flash (Medium)`
- **Total Session Development Prompts:** ~38,500 tokens
- **Total Session Generated Code/Artifacts:** ~14,200 tokens
- **Total Estimated Development Cost:** ~$0.016 USD

---

## 4. Run Execution Summary & Verification

- **Case Count:** 518 / 518 (100.0% completion)
- **Status Distribution:**
  - `COMPLETE`: 190 cases (36.7%)
  - `INCOMPLETE`: 318 cases (61.4%)
  - `NOT_APPLICABLE`: 10 cases (1.9%)
- **Total Generated Audit Steps:** 2,614 steps across active cases (average 5.15 steps/active case)
- **Memory Consumption:** < 120 MB peak resident memory
- **Exit Status:** Code 0 (Success)
