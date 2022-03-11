# DecisionCentral
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

DecisionCentral listens for http requests on port 7777 by default. The -p portNo option lets you assign a different port. However, DecisionCental can also be run in a container (it uses no disk storage - see the dockerfile) and you can use containter port mapping to map your desired port to 7777.

DecisionCentral can be run locally (see -h option for details).  
However can also be run in a container - dockerfile can be used to build a Docker image  
\$ docker build -t decisioncentral:0.0.1 .  
And run under Docker Desktop  
\$ docker run --name decisioncentral -p 7777:7777 -d decisioncentral:0.0.1

There is a flask version of DecisionCentral which can also be run in a docker container
NOTE: The flask versions listens for http requests on port 5000

questioner.py is a client that calls a specified Decision Central API, passing data from questions.csv and storing the decisions in answers.csv

DecisionCentral is not, of itself, a production product. You use pyDMNrules to build those.  
It is intended for use at Hackathons and Connectathons; anywhere you need a complex decision service created quickly and easily.
