{{/* Base name, overridable. */}}
{{- define "ecc.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully-qualified release name. */}}
{{- define "ecc.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ecc.backend.fullname" -}}
{{- printf "%s-backend" (include "ecc.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ecc.ui.fullname" -}}
{{- printf "%s-ui" (include "ecc.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ecc.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels shared by all resources. */}}
{{- define "ecc.labels" -}}
helm.sh/chart: {{ include "ecc.chart" . }}
app.kubernetes.io/name: {{ include "ecc.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Per-component selector labels.
Usage: include "ecc.selectorLabels" (dict "root" $ "component" "backend")
*/}}
{{- define "ecc.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ecc.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "ecc.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "ecc.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Build a full image reference, honoring global.imageRegistry override and an
AppVersion tag fallback.
Usage: include "ecc.image" (dict "root" $ "image" .Values.backend.image)
*/}}
{{- define "ecc.image" -}}
{{- $reg := .image.registry -}}
{{- with .root.Values.global }}
{{- if .imageRegistry }}{{- $reg = .imageRegistry -}}{{- end }}
{{- end -}}
{{- $tag := .image.tag | default .root.Chart.AppVersion -}}
{{- if $reg -}}
{{- printf "%s/%s:%s" $reg .image.repository $tag -}}
{{- else -}}
{{- printf "%s:%s" .image.repository $tag -}}
{{- end -}}
{{- end -}}

{{/* Render imagePullSecrets from global.imagePullSecrets (list of names). */}}
{{- define "ecc.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end -}}
{{- end -}}

{{/* In-cluster URL the UI uses to reach the backend, unless overridden. */}}
{{- define "ecc.backendUrl" -}}
{{- if .Values.ui.backendUrl -}}
{{- .Values.ui.backendUrl -}}
{{- else -}}
{{- printf "http://%s:%v" (include "ecc.backend.fullname" .) .Values.backend.service.port -}}
{{- end -}}
{{- end -}}
