# Agentic AI Project Ideas

This file preserves the original project shortlist for future builds.

## 1. AI Cloud Incident Commander — recommended and implemented here

An evidence-based incident investigation system. Lambda receives CloudWatch or webhook events; SQS buffers them; LangGraph agents on EKS triage logs and metrics, form a root-cause hypothesis, retrieve a runbook, and produce a report. Remediation remains behind human approval.

**Learning value:** LangGraph state and branching, multi-agent design, Python APIs/workers, event-driven Lambda, queues, containers, Kubernetes/EKS, IAM, observability, and infrastructure as code.

## 2. Disaster-Response Resource Coordinator

Agents validate reports, classify location and severity, match resources, plan routes, and prepare a human-approved allocation proposal. Lambda ingests reports and alerts; EKS runs geospatial and optimization workers; DynamoDB tracks incidents; S3 stores maps and reports; SNS delivers approved notifications.

## 3. Public-Benefits Navigation Assistant

Agents collect an intake, inspect official eligibility rules, identify supporting documents, check consistency, and explain possible programs with citations. Lambda handles submissions/uploads; EKS runs document processing and LangGraph; S3 holds encrypted uploads; DynamoDB stores workflow state; Textract extracts forms. It advises but does not make authoritative eligibility decisions.

## 4. Open-Source Security Triage Agent

Agents ingest advisories, inspect dependency graphs, analyze repositories, estimate exploitability, and draft patch guidance. Lambda receives GitHub webhooks; SQS distributes work; EKS runs sandboxed analysis workers; S3 stores artifacts; DynamoDB tracks findings. Untrusted code execution must be isolated.

## 5. Environmental Compliance Evidence Assistant

Agents classify documents, extract requirements, match evidence, identify gaps, assess risk, and generate a traceable review package. Lambda responds to uploads; EKS runs OCR post-processing, retrieval, and workflows; S3 stores documents; DynamoDB stores requirements; EventBridge schedules recurring checks.

## Selection criteria

A strong project should solve a recognizable problem, give every AWS service a real responsibility, preserve evidence and auditability, keep humans in control of consequential actions, and include repeatable evaluation rather than only a chatbot demo.
