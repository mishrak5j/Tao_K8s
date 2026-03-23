FROM python:3.9-slim
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files into the /app/src/ directory
COPY src/ ./src/

# Using ENTRYPOINT allows the K8s "args" to choose the script
ENTRYPOINT ["python"]