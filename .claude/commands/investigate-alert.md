Investigate the firing alert: $ARGUMENTS

Follow the investigation approach in CLAUDE.md:
1. Check pod status and Warning events in the affected namespace
2. Query Prometheus for error rate, restarts, CPU/memory
3. Fetch recent error logs from Loki
4. If database-related, check RDS status and CloudWatch metrics
5. Check ArgoCD sync health

Return a structured report:
- **Alert**: name and severity
- **What is happening**: one sentence
- **Evidence**: bullet list of findings from each tool
- **Root cause**: most likely explanation
- **Fix**: exact kubectl/aws commands to resolve it
