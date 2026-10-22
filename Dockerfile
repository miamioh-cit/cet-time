FROM python:3.12-slim
WORKDIR /app
RUN groupadd --gid 10001 tracker && useradd --uid 10001 --gid 10001 --create-home tracker && mkdir /app/data && chown tracker:tracker /app/data
COPY --chown=tracker:tracker server.py engine.py storage_check.py ./
COPY --chown=tracker:tracker static ./static
USER tracker
EXPOSE 8080
CMD ["python", "server.py"]
