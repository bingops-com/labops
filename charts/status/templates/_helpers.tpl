{{/*
Return the chart name
*/}}
{{- define "status.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Return the fully qualified name of the release
*/}}
{{- define "status.fullname" -}}
{{- if .Values.fullnameOverride -}}
  {{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
  {{- $name := include "status.name" . -}}
  {{- if contains $name .Release.Name -}}
    {{- .Release.Name | trunc 63 | trimSuffix "-" -}}
  {{- else -}}
    {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
  {{- end -}}
{{- end -}}
{{- end }}

{{/*
Labels identifying the pods; used by the selectors, so they never change
*/}}
{{- define "status.selectorLabels" -}}
app.kubernetes.io/name: {{ include "status.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Labels set on every object
*/}}
{{- define "status.labels" -}}
{{ include "status.selectorLabels" . }}
{{- with .Values.extraLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}
