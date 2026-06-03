FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY ch_converter ./ch_converter

EXPOSE 8000
CMD ["python", "-m", "ch_converter.main"]
