Give a full health summary of the Bookgate cluster.

Check:
1. All pods in `bookgate` and `monitoring` namespaces — any not Running/Ready?
2. Firing alerts: `curl -s http://kube-prometheus-stack-prometheus.monitoring.svc:9090/api/v1/alerts`
3. ArgoCD app health: `kubectl get applications -n argocd`
4. Recent Warning events across all namespaces: `kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20`
5. Node status: `kubectl get nodes`
6. Resource pressure: `kubectl top nodes && kubectl top pods -n bookgate`

Return a traffic-light summary:
- 🟢 Healthy
- 🟡 Degraded (with details)
- 🔴 Critical (with details)
