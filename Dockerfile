# Dockerfile

# Use Python 3.10-slim as base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements.txt file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask app code
COPY . .

# Set the Flask application environment variable
ENV FLASK_APP=app.py

# Expose the default Flask port
EXPOSE 5000

# Command to run the application
CMD ["flask", "run", "--host=0.0.0.0"]