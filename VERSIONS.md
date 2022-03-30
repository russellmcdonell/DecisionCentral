### 0.0.7 - added missing </body> and </html> tags
 - Set the return status for successful uploads to 201
 - Added OpenAPI specification for file upload
### 0.0.6 Added color to titles for Glossary and Decision
 - Added support for Glossary names and Decision names
 - Added support for Glossary annotations
 - Made the first Glossary annotation hints for the User Input form
### 0.0.5 Updated requirements to the latest version of pyDMNrules
 - for both main version (for docker) and flask version (also for docker)
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

