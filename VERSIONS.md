### 0.0.4 Added Status to returned JSON
 - Updated questioner.py for new Status
 - Created flask version of Decision Central
 - Fixed bug (not returning Executed Decision in JSON)
### 0.0.3 Fixed API bugs, added questioner.py and DMNexamples
 - questioner.py reads input data from a CSV file and exercises the API in Decision Central
 - DMNexamples contains DMN compliant workbooks which are know to work with pyDMNrules
### 0.0.2 - Added -p option for assiging port
 - DecisionCentral listens, by default, on port 7777 for http requests. The -p portNo option was added so that you can assign the listening port. As an alternative, you can run DecisionCentrol in a container (see docerfile) and map the port at run time.
### 0.0.1 - First version

