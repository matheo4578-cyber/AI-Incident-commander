# Security model

## Implemented controls

- Investigation-only graph; no production mutation tools or permissions.
- Every report requires human approval.
- Input length bounds and Pydantic validation.
- Least-privilege Lambda IAM: logs and one SQS `SendMessage` action.
- Separate IRSA roles: the private API can only read/write reports; the worker can only consume its queue and create reports.
- SQS and DynamoDB encryption; private, encrypted, versioned S3 bucket.
- ECR immutable tags, encryption, and scan-on-push.
- Kubernetes restricted pod security, non-root UID, dropped capabilities, read-only root filesystems, resource limits, and health probes.
- OpenAI key is a Kubernetes Secret and is excluded from Terraform state and Git.
- Lambda and EventBridge are AWS-IAM controlled; there is no anonymous Lambda URL.
- The EKS API is limited to operator-provided CIDRs, and the dashboard is a private `ClusterIP` reached through an authenticated `kubectl port-forward` session.
- Incident IDs are generated at trusted boundaries; report writes are create-only in S3 and DynamoDB to prevent replacement.
- DynamoDB is the canonical report record; duplicate deliveries reconcile S3 from that record, and the SQS worker extends message visibility while an investigation is running.

## Production hardening still required

The default deployment creates no public application endpoint. If you intentionally add an Ingress or public load balancer for shared production use:

1. Put HTTPS in front with ACM and an AWS Load Balancer Controller/Ingress.
2. Add OIDC/SSO authentication and authorization.
3. Restrict network access to a VPN, Tailscale subnet route, approved CIDRs, or a private load balancer.
4. Add WAF/rate limits and request-size controls at the edge.
5. Scrub secrets/PII before persistence or model calls.
6. Use KMS customer-managed keys and a managed secret store if policy requires them.
7. Add CloudTrail, GuardDuty, audit-log retention, backups, and alerting.
8. Evaluate prompt injection from logs and require evidence citations for every claim.
9. Pin base images by digest and sign/verify images for a stronger software supply chain.

## Threat boundaries

Logs and alert text are untrusted data, not instructions. Agents are prompted to use supplied evidence and are not given shell, kubectl, database-write, or AWS-mutation tools. Confidence is a model output, not proof. Human operators must verify the evidence in the source monitoring systems.
