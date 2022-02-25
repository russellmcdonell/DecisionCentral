# DecisionCentral
DecisionCentral is a central repository for all DMN based decision services.  

DecisionCentral  
* Lets you upload a DMN compliant Excel workbook
* Will create a decision service from that DMN compliant workbook
* Creates a user interface so that you can enter values and check specific use cases for this decision service
* Creates an API which accepts JSON data and returns a JSON structure representing the decision, from this decision service, based upon that data.
* Creates web pages detailing all the parts of your decision service
  - The glossary of data items, both inputs and outputs, associated with this decision service
  - The decision sequence (the sequence in which you decision tables will be run)
  - The decision tables that form this decision service
* Creates an OpenAPI specification the the api associated with this decision service - displayed as a web page, but it can also be downloaded and imported to Postman/Swagger etc.

DecisionCentral is not, of itself, a production product. You use pyDMNrules to build those. It is intended for use at Hackathons and Connectathons; anywhere you need a complex decision service created quickly and easily.
