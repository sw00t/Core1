# One image for every sample service; CORE1_SERVICE selects the module at start.
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}
ARG SERVICE=gateway
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080 CORE1_SERVICE=${SERVICE}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 -d /app app
COPY core1app ./core1app
USER 10001
EXPOSE 8080
CMD ["python", "-m", "core1app"]
