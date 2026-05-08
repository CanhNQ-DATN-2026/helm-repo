Check RDS health for the Bookgate database.

Run these checks:
1. Instance status via `aws rds describe-db-instances`
2. Recent events via `aws rds describe-events` (last 60 minutes)
3. CloudWatch metrics: DatabaseConnections, FreeStorageSpace, CPUUtilization, ReadLatency, WriteLatency
4. Check ESO secret sync: `kubectl get externalsecrets -n bookgate`
5. Check if api-service pods can resolve the DB host: `kubectl exec -n bookgate deploy/api-service -- nslookup bookgate-dev-postgres.c676gkw8k630.us-east-1.rds.amazonaws.com`

Summarize: status, connection count, storage remaining, any anomalies.
