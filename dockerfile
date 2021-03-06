# Use the latest Python container base image
FROM python:latest

# Set the working directory
WORKDIR /usr/app/DecisionCentral

# Copy DecisionCentral.py and requirements.txt to here (.)
COPY DecisionCentral.py .
COPY requirements.txt .

# Update Python with the requirements
RUN python -m pip install -r ./requirements.txt

# Now run DecisionCentral
CMD [ "python", "./DecisionCentral.py" ]
