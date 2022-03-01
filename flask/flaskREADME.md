# A Flask version of DecisionCentral
DecisionCentral is a central repository for all DMN based decision services.  

DecisionCentral  
* Lets you upload DMN compliant Excel workbooks
* Each uplaoded DMN compliant Excell workbook will
  - create a decision service from that DMN compliant workbook
  - create a user interface so that you can enter values and check specific use cases for this decision service
  - creates an API for this decision service which accepts JSON data (the input values) and returns a JSON structure (representing the decision) from this decision service, based upon that data input data.
  - creates web pages detailing all the parts of your decision service
    - The glossary of data items, both inputs and outputs, associated with this decision service
    - The decision sequence (the sequence in which you decision tables will be run)
    - The decision tables that form this decision service
  - creates an OpenAPI specification for the the API associated with this decision service
    - It will be displayed as a web page, but it can also be downloaded and imported to Postman/Swagger etc.

The Flask version of DecisionCentral listens for http requests on port 5000 by default.

The Flask version DecisionCentral can be run locally ($ python3 DecisionCentral.py)
However can also be run in a container - dockerfile can be used to build a Docker image  
\$ docker build -t flaskdecisioncentral:0.0.1 .  
And run under Docker Desktop  
\$ docker run --name flaskdockercentral -p 5000:5000 -d flaskdecisioncentral:0.0.1

DecisionCentral is not, of itself, a production product. You use pyDMNrules to build those.  
It is intended for use at Hackathons and Connectathons; anywhere you need a complex decision service created quickly and easily.
