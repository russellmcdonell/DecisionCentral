# DecisionCentral
DecisionCentral is a central repository for all DMN based decision services.  

DecisionCentral  
* Creates a web site that lets you upload DMN compliant Excel workbooks or DMN conformant XML files
* For each uploaded DMN compliant Excel workbook or DMN compliant XML file, DecisionCentral will
  - create a decision service from that DMN compliant Excel workbook or DMN conformant XML file
  - create a user interface where users can enter values and check specific use cases for this decision service
  - creates an API for this decision service which accepts JSON data (the input values) and returns a JSON structure (representing the decision)    
* For each decision service, DecisionCentral will create web pages detailing all the parts of your decision service
    - The glossary of data items, both inputs and outputs, associated with this decision service
    - The decision sequence (the sequence in which you decision tables will be run)
    - The decision tables that form this decision service
    - An OpenAPI specification for the the API associated with this decision service which will be displayed as a web page, but it can also be downloaded and imported to Postman/Swagger etc.
* For each decision table, within each decision service, DecisionCentral will
  - create a DMN compliant representation of the rules built when the decision service was created
  - create a user interface where users can enter values and check specific use cases for this decision table within this decision service
  - create an API for this decision table within this decision service which accepts JSON data (the input values) and returns a JSON structure (representing the decision)    
  - createe an OpenAPI specification for the the API associated with this decision table with this decision service which will be displayed as a web page, but it can also be downloaded and imported to Postman/Swagger etc.

DecisionCentral also has an API for uploading a DMN compliant Excel workbook or DMN conformant XML file, plus and API for deleting a decision service.

DecisionCentral listens for http requests on port 7777 by default. The -p portNo option lets you assign a different port. However, DecisionCental can also be run in a container (it uses no disk storage - see the dockerfile) and you can use containter port mapping to map your desired port to 7777.

DecisionCentral can be run locally (see -h option for details).  
However can also be run in a container - dockerfile can be used to build a Docker image  
\$ docker build -t decisioncentral:0.0.1 .  
And run under Docker Desktop  
\$ docker run --name decisioncentral -p 7777:7777 -d decisioncentral:0.0.1

There is a **flask** version of DecisionCentral which is the reference version. It can also be run in a docker container and the basis for [DecisionCentralAzure] (https://github.com/russellmcdonell/DecisionCentralAzure) - a version which creates an Azure Program as a Platform instance of DecisionCentral.
NOTE: The flask versions listens for http requests on port 5000, and it too can be run in a container.

JSON and DMN data types
JSON doesn't support all the data types that are supported by DMN (and the FEEL expression language).
Decision Central borrows a solution suggested by FEEL - @strings.
If a string starts with the two characters @" and ends with the character " then what is in between has to be de-serialized by some other non-JSON interpreter.
In this case, the FEEL interpreter (pySFeel).
The following code can be used to serialize and de-serialize @strings.

    import datetime
    import pySFeel

    parser = pySFeel.SFeelParser()


    def convertAtString(thisString):
        # Convert an @string
        (status, newValue) = parser.sFeelParse(thisString[2:-1])
        if 'errors' in status:
            return thisString
        else:
            return newValue


    def convertIn(newValue):
        if isinstance(newValue, dict):
            for key in newValue:
                if isinstance(newValue[key], int):
                    newValue[key] = float(newValue[key])
                elif isinstance(newValue[key], str) and (newValue[key][0:2] == '@"') and (newValue[key][-1] == '"'):
                    newValue[key] = convertAtString(newValue[key])
                elif isinstance(newValue[key], dict) or isinstance(newValue[key], list):
                    newValue[key] = convertIn(newValue[key])
        elif isinstance(newValue, list):
            for i in range(len(newValue)):
                if isinstance(newValue[i], int):
                    newValue[i] = float(newValue[i])
                elif isinstance(newValue[i], str) and (newValue[i][0:2] == '@"') and (newValue[i][-1] == '"'):
                    newValue[i] = convertAtString(newValue[i])
                elif isinstance(newValue[i], dict) or isinstance(newValue[i], list):
                    newValue[i] = convertIn(newValue[i])
        elif isinstance(newValue, str) and (newValue[0:2] == '@"') and (newValue[-1] == '"'):
            newValue = convertAtString(newValue)
        return newValue


      def convertOut(thisValue):
          if isinstance(thisValue, datetime.date):
              return '@"' + thisValue.isoformat() + '"'
          elif isinstance(thisValue, datetime.datetime):
              return '@"' + thisValue.isoformat(sep='T') + '"'
          elif isinstance(thisValue, datetime.time):
              return '@"' + thisValue.isoformat() + '"'
          elif isinstance(thisValue, datetime.timedelta):
              sign = ''
              duration = thisValue.total_seconds()
              if duration < 0:
                  duration = -duration
                  sign = '-'
              secs = duration % 60
              duration = int(duration / 60)
              mins = duration % 60
              duration = int(duration / 60)
              hours = duration % 24
              days = int(duration / 24)
              return '@"%sP%dDT%dH%dM%fS"' % (sign, days, hours, mins, secs)
          elif isinstance(thisValue, bool):
              return thisValue:
          elif thisValue is None:
              return thisValue:
          elif isinstance(thisValue, int):
              sign = ''
              if thisValue < 0:
                  thisValue = -thisValue
                  sign = '-'
              years = int(thisValue / 12)
              months = (thisValue % 12)
              return '@"%sP%dY%dM"' % (sign, years, months)
          elif isinstance(thisValue, tuple) and (len(thisValue) == 4):
              (lowEnd, lowVal, highVal, highEnd) = thisValue
              return '@"' + lowEnd + str(lowVal) + ' .. ' + str(highVal) + highEnd
          elif thisValue is None:
              return 'null'
          elif isinstance(thisValue, dict):
              for item in thisValue:
                  thisValue[item] = convertOut(thisValue[item])
              return thisValue
          elif isinstance(thisValue, list):
              for i in range(len(thisValue)):
                  thisValue[i] = convertOut(thisValue[i])
              return thisValue
          else:
              return thisValue


questioner.py is a client that calls a specified Decision Central API, passing data from questions.xlsx and storing the decisions in answers.xlsx

DecisionCentral is not, of itself, a production product. You use pyDMNrules to build those.  
It is intended for use at Hackathons and Connectathons; anywhere you need a complex decision service created quickly and easily.
