FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY ch_converter ./ch_converter
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["python", "-m", "ch_converter.main"]
