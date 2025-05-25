{{/*
Return the fully qualified name of the chart
*/}}
{{- define "www.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | replace "." "-" | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Return the chart name
*/}}
{{- define "www.name" -}}
{{- .Chart.Name -}}
{{- end }}
