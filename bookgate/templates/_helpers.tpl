{{/*
Full ECR image reference.
Usage: {{ include "bookgate.image" (dict "registry" .Values.ecr.registry "repo" .Values.apiService.image.repository "tag" .Values.apiService.image.tag) }}
*/}}
{{- define "bookgate.image" -}}
{{- printf "%s/%s:%v" .registry .repo .tag -}}
{{- end }}

{{- define "bookgate.name" -}}
{{- .Release.Name }}
{{- end }}

{{- define "bookgate.namespace" -}}
{{- .Release.Namespace }}
{{- end }}
