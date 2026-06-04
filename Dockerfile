FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY ch_converter ./ch_converter
RUN pip install --no-cache-dir .

# Run unprivileged. uid 1001 satisfies runAsNonRoot on plain Kubernetes; on
# OpenShift the SCC assigns an arbitrary uid in group 0 instead, which also
# works since the app needs no writable paths and site-packages is world-read.
RUN useradd --uid 1001 --gid 0 --no-create-home --shell /sbin/nologin appuser
USER 1001

EXPOSE 8000
CMD ["python", "-m", "ch_converter.main"]
