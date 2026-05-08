{{/*
Expand the name of the chart.
*/}}
{{- define "aiops-bot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "aiops-bot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "aiops-bot.labels" -}}
helm.sh/chart: {{ include "aiops-bot.chart" . }}
{{ include "aiops-bot.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "aiops-bot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aiops-bot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "aiops-bot.namespace" -}}
{{- default "bookgate" .Values.namespace }}
{{- end }}

{{/*
Full image path
*/}}
{{- define "aiops-bot.image" -}}
{{- printf "%s/%s:%s" .Values.ecr.registry .Values.image.repository .Values.image.tag }}
{{- end }}
