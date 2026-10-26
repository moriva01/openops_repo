FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY receiver receiver
COPY tests tests
RUN useradd --system --uid 10001 openops && mkdir /app/logs && chown openops /app/logs
USER openops
ENV PYTHONUNBUFFERED=1
EXPOSE 8096
CMD ["python", "-m", "receiver.server"]
