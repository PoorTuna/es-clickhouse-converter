# es-clickhouse-converter Helm chart

Deploys the **Elasticsearch → ClickHouse schema converter**: the FastAPI backend
and the React UI (nginx) that proxies to it. One release, two Deployments + two
Services, optional Ingress **or** OpenShift Route.

- **Air-gap friendly** — no subchart dependencies, all images configurable from a
  mirror via `global.imageRegistry`, `pullPolicy: IfNotPresent`, optional
  `global.imagePullSecrets`.
- **OpenShift ready** — runs under the `restricted-v2` SCC unchanged: no fixed
  uid, `runAsNonRoot`, all capabilities dropped, `seccompProfile: RuntimeDefault`.
  The UI image is unprivileged nginx on port 8080 with an auto-detected DNS
  resolver, so it works on Docker, plain Kubernetes and OpenShift.
- **Schema-validated** — `values.schema.json` validates every install/upgrade.

## Install

```sh
helm install converter ./helm/es-clickhouse-converter -n converter --create-namespace
```

### OpenShift (expose via Route)

```sh
helm install converter ./helm/es-clickhouse-converter -n converter --create-namespace \
  --set route.enabled=true
```

### Plain Kubernetes (expose via Ingress)

```sh
helm install converter ./helm/es-clickhouse-converter -n converter --create-namespace \
  --set ingress.enabled=true \
  --set ingress.host=converter.example.com \
  --set ingress.className=nginx
```

### Air-gapped (mirror registry)

Mirror both images to your registry, then:

```sh
helm install converter ./helm/es-clickhouse-converter -n converter --create-namespace \
  --set global.imageRegistry=registry.internal:5000 \
  --set global.imagePullSecrets={registry-creds}
```

`global.imageRegistry` prefixes **both** images; tags default to the chart
`appVersion` (currently `0.3.0`).

## Key values

| Key | Default | Description |
|-----|---------|-------------|
| `global.imageRegistry` | `""` | Mirror prefix for both images |
| `global.imagePullSecrets` | `[]` | Pull secret names for both pods |
| `backend.image.repository` | `poortuna/es-clickhouse-converter` | Backend image |
| `ui.image.repository` | `poortuna/es-clickhouse-converter-ui` | UI image |
| `*.image.tag` | `""` → `appVersion` | Image tag |
| `ui.backendUrl` | `""` (auto) | Override the in-cluster backend URL |
| `ui.resolver` | `""` (auto) | Pin nginx DNS resolver instead of auto-detect |
| `ingress.enabled` | `false` | Expose UI via Ingress |
| `route.enabled` | `false` | Expose UI via OpenShift Route |
| `networkPolicy.enabled` | `false` | Restrict backend to UI-only ingress |
| `*.autoscaling.enabled` | `false` | HPA per component |

See `values.yaml` for the full set and `values.schema.json` for constraints.

## Validate

```sh
helm lint ./helm/es-clickhouse-converter
helm template converter ./helm/es-clickhouse-converter --set route.enabled=true | kubectl apply --dry-run=client -f -
```

## Images

Built from the sibling repos and pushed to Docker Hub:

- `poortuna/es-clickhouse-converter:0.3.0` (backend, non-root uid 1001)
- `poortuna/es-clickhouse-converter-ui:0.3.0` (UI, unprivileged nginx :8080)
