# EraseVerify-AI 🔐
### AI-Powered Data Deletion Verification System

## 📌 Overview

**EraseVerify-AI** is an AI-powered data deletion verification system designed to identify personal information that remains in an organization's systems after a user requests its deletion.

Deleting data from one location does not always remove it from databases, application logs, exported files, backups, or connected services. EraseVerify-AI analyses available evidence to detect incomplete deletions, exposed personal information, active data flows, and backup restoration risks.

Using evidence-based analysis and policy-driven rules, the system classifies deletion requests and generates actionable remediation and verification steps to support reliable, transparent, and verifiable data deletion.

## 🎯 Problem Statement

Organizations may struggle to verify whether personal data has been completely deleted across all systems. Residual records, active synchronization processes, and backup restoration mechanisms can cause deleted information to reappear or remain accessible.

EraseVerify-AI addresses this challenge by analysing available evidence and identifying potential gaps in the data deletion process.

## 💡 Key Features

- **Identity Resolution:** Identifies relevant records associated with a deletion request.
- **Multi-Format Evidence Analysis:** Extracts relevant information from supported databases, JSON files, logs, text documents, PDFs, and images.
- **Deletion Status Classification:** Categorizes requests as `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- **Privacy Risk Detection:** Identifies remaining personal information and potential data exposure.
- **Data Flow Analysis:** Detects evidence of active synchronization or other processes that may recreate deleted data.
- **Backup Restoration Risk Detection:** Identifies potential risks associated with restoring previously deleted information.
- **Policy-Driven Remediation:** Generates ordered actions based on applicable deletion and retention rules.
- **Evidence-Based Verification:** Uses available evidence to support deletion status decisions and verification steps.
- **Structured Output:** Produces results in the required CSV format for evaluation and further analysis.

## ⚙️ How It Works

1. **Input Processing:** Reads deletion requests, policy rules, and available evidence files.
2. **Identity Resolution:** Determines which records and identifiers are relevant to each request.
3. **Evidence Extraction:** Collects relevant facts from supported file formats and system records.
4. **Fact Aggregation:** Combines extracted evidence into a structured representation.
5. **Policy Evaluation:** Evaluates deletion status according to applicable rules and evidence.
6. **Remediation Planning:** Generates ordered steps for addressing unresolved deletion issues.
7. **Output Generation:** Produces a structured CSV containing the deletion status and corresponding steps.

## 🧰 Technology Stack

- **Programming Language:** Python
- **Data Processing:** CSV, JSON, and structured text processing
- **Document Analysis:** PDF and text extraction tools
- **Image Analysis:** OCR-based text extraction where supported
- **Decision Engine:** Rule-based policy evaluation
- **Testing:** Automated tests and evaluation against available test cases

*The exact dependencies and optional integrations depend on the project configuration.*

## 📊 Deletion Statuses

| Status | Description |
|---|---|
| `COMPLETE` | Available evidence supports that the applicable deletion requirements have been satisfied. |
| `INCOMPLETE` | Evidence indicates unresolved deletion requirements or risks. |
| `NOT_APPLICABLE` | The deletion request does not apply under the defined rules. |

## 📁 Project Structure

The project is organized into modules for identity resolution, request classification, evidence extraction, policy evaluation, remediation planning, and output generation.

```text
EraseVerify-AI/
├── code/
│   ├── evidence_extractors/
│   ├── fact_aggregator.py
│   ├── policy_engine.py
│   ├── step_builder.py
│   └── main.py
├── tests/
├── dataset/
├── README.md
└── log.txt
```

*This is a representative structure. Update it to match the final contents of your repository.*

## 🚀 Getting Started

### Prerequisites

- Python 3.x
- Git
- A code editor such as Visual Studio Code

### Installation

Clone the repository:

```bash
git clone <YOUR_REPOSITORY_URL>
```

Navigate to the project directory:

```bash
cd <YOUR_PROJECT_DIRECTORY>
```

Install the dependencies listed in the project's requirements file, if one is provided:

```bash
pip install -r requirements.txt
```

### Running the Project

Run the entry-point script using the command specified by the project's configuration. For example:

```bash
python code/main.py
```

Ensure that the required input files and configuration are available before execution. Adjust the command if the project uses a different entry point or requires command-line arguments.

## 🧪 Testing

Run the project's automated tests using the configured test framework. If the project uses `pytest`, run:

```bash
python -m pytest
```

Use the provided evaluation scripts and test cases to validate classification accuracy, evidence handling, remediation ordering, and output formatting.

## 🔒 Privacy and Responsible Data Handling

EraseVerify-AI is designed to analyse evidence for deletion verification. It does not automatically guarantee that data has been physically erased from every system. Its conclusions depend on the evidence, policies, and inputs available to it.

Sensitive data and evaluation datasets should be handled securely. Any production deployment should include appropriate access controls, audit logging, and safeguards against unauthorized disclosure.

## 🌍 Potential Impact

EraseVerify-AI aims to help organizations:

- Improve confidence in personal data deletion.
- Identify residual personal information and privacy risks.
- Detect potential data recreation pathways.
- Apply consistent, policy-driven remediation procedures.
- Improve the transparency and auditability of deletion workflows.

## 🔮 Future Enhancements

- Integration with live databases and enterprise storage systems.
- Support for additional document formats and evidence sources.
- Improved OCR and intelligent evidence extraction.
- Automated monitoring of data synchronization and backup restoration.
- Interactive dashboards for deletion status and compliance reporting.

## 🤝 Contributing

Contributions, suggestions, and improvements are welcome. Please test changes thoroughly and ensure that new features preserve evidence integrity, policy compliance, and the required output format.

## 📄 License

Add a license file and specify the applicable license before distributing or reusing this project.

---

**EraseVerify-AI — Making data deletion more transparent, accountable, and verifiable.**
