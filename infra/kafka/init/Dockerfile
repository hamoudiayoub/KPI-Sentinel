# Applies infra/kafka/topics.yaml with the Kafka CLI tools of the broker image.
FROM apache/kafka:4.4.0

USER root
RUN apk add --no-cache python3 py3-yaml
COPY apply_topics.py /opt/kafka-init/apply_topics.py
USER appuser

ENTRYPOINT ["python3", "/opt/kafka-init/apply_topics.py"]
