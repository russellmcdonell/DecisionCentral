#!/usr/bin/env python

'''
A script to build a web site as a central repository for DMN decision service.
This is a flask version of DecisionCentral

SYNOPSIS
$ export FLASK_APP=DecisionCentral
$ python3 -m flask run


This script lets users upload Excel workbooks, which must comply to the DMN standard.
Once an Excel workbook has been uploaded and parsed successfully as a DMN complient workbook, this script will
1. Create a dedicated web page so that the user can interactively run/check their decision service
2. Create an API so that the user can use, programatically, their decision service
3. Create an OpenAPI yaml file documenting the created API

'''

# Import all the modules that make life easy
import io
import sys
import datetime
import dateutil.parser, dateutil.tz
from flask import Flask, flash, abort, jsonify, url_for, request, render_template, redirect, send_file, Response
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename
from urllib.parse import urlparse, urlencode, parse_qs, quote, unquote
from openpyxl import load_workbook
import pyDMNrules
import pySFeel
import copy
import logging

Excel_EXTENSIONS = {'xlsx', 'xlsm'}
ALLOWED_EXTENSIONS = {'xlsx', 'xlsm', 'xml', 'dmn'}

app = Flask(__name__)

decisionServices = {}        # The dictionary of currently defined Decision services
lexer = pySFeel.SFeelLexer()

def mkOpenAPI(glossary, name):
    thisAPI = []
    thisAPI.append('openapi: 3.0.0')
    thisAPI.append('info:')
    thisAPI.append('  title: Decision Service {}'.format(name))
    thisAPI.append('  version: 1.0.0')
    if ('X-Forwarded-Host' in request.headers) and ('X-Forwarded-Proto' in request.headers):
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}://{}"'.format(request.headers['X-Forwarded-Proto'], request.headers['X-Forwarded-Host']))
        thisAPI.append('  ]')
    elif 'Host' in request.headers:
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}"'.format(request.headers['Host']))
        thisAPI.append('  ]')
    elif 'Forwarded' in request.headers:
        forwards = request.headers['Forwarded'].split(';')
        origin = forwards[0].split('=')[1]
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}"'.format(origin))
        thisAPI.append('  ]')
    thisAPI.append('paths:')
    thisAPI.append('  /api/{}:'.format(quote(name)))
    thisAPI.append('    post:')
    thisAPI.append('      summary: Use the {} Decision Service to make a decision based upon the passed data'.format(name))
    thisAPI.append('      operationId: decide')
    thisAPI.append('      requestBody:')
    thisAPI.append('        description: json structure with one tag per item of passed data')
    thisAPI.append('        content:')
    thisAPI.append('          application/json:')
    thisAPI.append('            schema:')
    thisAPI.append("              $ref: '#/components/schemas/decisionInputData'")
    thisAPI.append('        required: true')
    thisAPI.append('      responses:')
    thisAPI.append('        200:')
    thisAPI.append('          description: Success')
    thisAPI.append('          content:')
    thisAPI.append('            application/json:')
    thisAPI.append('              schema:')
    thisAPI.append("                $ref: '#/components/schemas/decisionOutputData'")
    thisAPI.append('components:')
    thisAPI.append('  schemas:')
    thisAPI.append('    decisionInputData:')
    thisAPI.append('      type: object')
    thisAPI.append('      properties:')
    for concept in glossary:
        for variable in glossary[concept]:
            thisAPI.append('        "{}":'.format(variable))
            thisAPI.append('          type: string')
    thisAPI.append('    decisionOutputData:')
    thisAPI.append('      type: object')
    thisAPI.append('      properties:')
    thisAPI.append('        "Result":')
    thisAPI.append('          type: object')
    thisAPI.append('          properties:')
    for concept in glossary:
        for variable in glossary[concept]:
            thisAPI.append('            "{}":'.format(variable))
            thisAPI.append('              type: object')
            thisAPI.append('              additionalProperties:')
            thisAPI.append('                oneOf:')
            thisAPI.append('                  - type: string')
            thisAPI.append('                  - type: array')
            thisAPI.append('                    items:')
            thisAPI.append('                      type: string')
    thisAPI.append('        "Executed Rule":')
    thisAPI.append('          type: array')
    thisAPI.append('          items:')
    thisAPI.append('            additionalProperties:')
    thisAPI.append('              oneOf:')
    thisAPI.append('                - type: string')
    thisAPI.append('                - type: array')
    thisAPI.append('                  items:')
    thisAPI.append('                    type: string')
    thisAPI.append('        "Status":')
    thisAPI.append('          type: object')
    thisAPI.append('          properties:')
    thisAPI.append('            "errors":')
    thisAPI.append('              type: array')
    thisAPI.append('              items:')
    thisAPI.append('                type: string')
    thisAPI.append('      required: [')
    thisAPI.append('        "Result",')
    thisAPI.append('        "Executed Rule",')
    thisAPI.append('        "Status"')
    thisAPI.append('      ]')
    return '\n'.join(thisAPI)


def mkUploadOpenAPI():
    thisAPI = []
    thisAPI.append('openapi: 3.0.0')
    thisAPI.append('info:')
    thisAPI.append('  title: Decision Service file upload API')
    thisAPI.append('  version: 1.0.0')
    if ('X-Forwarded-Host' in request.headers) and ('X-Forwarded-Proto' in request.headers):
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}://{}"'.format(request.headers['X-Forwarded-Proto'], request.headers['X-Forwarded-Host']))
        thisAPI.append('  ]')
    elif 'Host' in request.headers:
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}"'.format(request.headers['Host']))
        thisAPI.append('  ]')
    elif 'Forwarded' in request.headers:
        forwards = request.headers['Forwarded'].split(';')
        origin = forwards[0].split('=')[1]
        thisAPI.append('servers:')
        thisAPI.append('  [')
        thisAPI.append('    "url":"{}"'.format(origin))
        thisAPI.append('  ]')
    thisAPI.append('paths:')
    thisAPI.append('  /upload:')
    thisAPI.append('    post:')
    thisAPI.append('      summary: Upload a file to DecisionCentral')
    thisAPI.append('      operationId: upload')
    thisAPI.append('      requestBody:')
    thisAPI.append('        description: json structure with one tag per item of passed data')
    thisAPI.append('        content:')
    thisAPI.append('          multipart/form-data:')
    thisAPI.append('            schema:')
    thisAPI.append("              $ref: '#/components/schemas/FileUpload'")
    thisAPI.append('        required: true')
    thisAPI.append('      responses:')
    thisAPI.append('        201:')
    thisAPI.append('          description: Item created')
    thisAPI.append('          content:')
    thisAPI.append('            text/html:')
    thisAPI.append('              schema:')
    thisAPI.append('                type: string')
    thisAPI.append('        400:')
    thisAPI.append('          description: Invalid input, object invalid')
    thisAPI.append('components:')
    thisAPI.append('  schemas:')
    thisAPI.append('    FileUpload:')
    thisAPI.append('      type: object')
    thisAPI.append('      properties:')
    thisAPI.append('        file:')
    thisAPI.append('          type: string')
    thisAPI.append('          format: binary')
    return '\n'.join(thisAPI)


def convertIn(thisValue):
    if isinstance(thisValue, int):
        return float(thisValue)
    elif isinstance(thisValue, dict):
        for item in thisValue:
            thisValue[item] = convertIn(thisValue[item])
    elif isinstance(thisValue, list):
        for i in range(len(thisValue)):
            thisValue[i] = convertIn(thisValue[i])
    elif isinstance(thisValue, str):
        if thisValue == '':
            return None
        tokens = lexer.tokenize(thisValue)
        yaccTokens = []
        for token in tokens:
            yaccTokens.append(token)
        if len(yaccTokens) != 1:
            if (thisValue[0] != '"') or (thisValue[-1] != '"'):
                return '"' + thisValue + '"'
            else:
                return thisValue
        elif yaccTokens[0].type == 'NUMBER':
                return float(thisValue)
        elif yaccTokens[0].type == 'BOOLEAN':
            if thisValue == 'true':
                return True
            elif thisValue == 'false':
                return False
            elif thisValue == 'null':
                return None
        elif yaccTokens[0].type == 'NAME':
            if thisValue == 'true':
                return True
            elif thisValue == 'True':
                return True
            elif thisValue == 'TRUE':
                return True
            elif thisValue == 'false':
                return False
            elif thisValue == 'False':
                return False
            elif thisValue == 'FALSE':
                return False
            elif thisValue == 'none':
                return None
            elif thisValue == 'None':
                return None
            elif thisValue == 'null':
                return None
            else:
                return thisValue
        elif yaccTokens[0].type == 'STRING':
            return thisValue[1:-1]
        elif yaccTokens[0].type == 'NUMBER':
            return float(thisValue)
        elif yaccTokens[0].type == 'DTDURATION':
            sign = 0
            if thisValue[0] == '-':
                sign = -1
                thisValue = thisValue[1:]     # skip -
            thisValue = thisValue[1:]         # skip P
            days = seconds = milliseconds = 0
            if thisValue[0] != 'T':          # days is optional
                parts = thisValue.split('D')
                if len(parts[0]) > 0:
                    days = int(parts[0])
                thisValue = parts[1]
            if len(thisValue) > 0:
                thisValue = thisValue[1:]         # Skip T
                parts = thisValue.split('H')
                if len(parts) == 2:
                    if len(parts[0]) > 0:
                        seconds = int(parts[0]) * 60 * 60
                    thisValue = parts[1]
                parts = thisValue.split('M')
                if len(parts) == 2:
                    if len(parts[0]) > 0:
                        seconds += int(parts[0]) * 60
                    thisValue = parts[1]
                parts = thisValue.split('S')
                if len(parts) == 2:
                    if len(parts[0]) > 0:
                        sPart = float(parts[0])
                        seconds += int(sPart)
                        milliseconds = int((sPart * 1000)) % 1000
            if sign == 0:
                return datetime.timedelta(days=days, seconds=seconds, milliseconds=milliseconds)
            else:
                return -datetime.timedelta(days=days, seconds=seconds, milliseconds=milliseconds)
        elif yaccTokens[0].type == 'YMDURATION':
            sign = 0
            if thisValue == '-':
                sign = -1
                thisValue = thisValue[1:]     # skip -
            thisValue = thisValue[1:]         # skip P
            months = 0
            parts = thisValue.split('Y')
            months = int(parts[0]) * 12
            parts = parts[1].split('M')
            if len(parts[0]) > 0:
                months += int(parts[0])
            if sign == 0:
                return int(months)
            else:
                return -int(months)
        elif yaccTokens[0].type == 'DATETIME':
            parts = thisValue.split('@')
            thisDateTime = dateutil.parser.parse(parts[0])
            if len(parts) > 1:
                thisZone = dateutil.tz.gettz(parts[1])
                if thisZone is not None:
                    try:
                        thisDateTime = thisDateTime.replace(tzinfo=thisZone)
                    except:
                        thisDateTime = thisDateTime
                    thisDateTime = thisDateTime
            return thisDateTime
        elif yaccTokens[0].type == 'DATE':
            return dateutil.parser.parse(thisValue).date()
        elif yaccTokens[0].type == 'TIME':
            parts = thisValue.split('@')
            thisTime =  dateutil.parser.parse(parts[0]).timetz()     # A time with timezone
            if len(parts) > 1:
                thisZone = dateutil.tz.gettz(parts[1])
                if thisZone is not None:
                    try:
                        thisTime = thisTime.replace(tzinfo=thisZone)
                    except:
                        thisTime = thisTime
                    thisTime = thisTime
            return thisTime
        else:
            return thisValue
    else:
        return thisValue


def convertOut(thisValue):
    if isinstance(thisValue, datetime.date):
        return thisValue.isoformat()
    elif isinstance(thisValue, datetime.datetime):
        return thisValue.isoformat(sep='T')
    elif isinstance(thisValue, datetime.time):
        return thisValue.isoformat()
    elif isinstance(thisValue, datetime.timedelta):
        duration = thisValue.total_seconds()
        secs = duration % 60
        duration = int(duration / 60)
        mins = duration % 60
        duration = int(duration / 60)
        hours = duration % 24
        days = int(duration / 24)
        return 'P%dDT%dH%dM%dS' % (days, hours, mins, secs)
    elif isinstance(thisValue, dict):
        for item in thisValue:
            thisValue[item] = convertOut(thisValue[item])
    elif isinstance(thisValue, list):
        for i in range(len(thisValue)):
            thisValue[i] = convertOut(thisValue[i])
    else:
        return thisValue


@app.route('/', methods=['GET'])
def splash():
    message = '<html><head><title>Decision Central</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
    message += '<h1 align="center">Welcolme to Decision Central</h1>'
    message += '<h3 align="center">Your home for all your DMN Decision Services</h3>'
    message += '<div align="center"><b>Here you can create a Decision Service by simply'
    message += '<br/>uploading a DMN compatible Excel workbook</b></div>'
    message += '<br/><table width="80%" align="center" style="font-size:120%">'
    message += '<tr>'
    message += '<th>With each created Decision Service you get</th>'
    message += '<th>Available Decision Services</th>'
    message += '</tr>'
    message += '<tr><td>'
    message += '<ol>'
    message += '<li>An API which you can use to test integration to you Decision Service'
    message += '<li>A user interface where you can perform simple tests of your Decision Service'
    message += '<li>A list of links to HTML renditions of the Decision Tables in your Decision Service'
    message += '<li>A link to the Open API YAML file which describes you Decision Service'
    message += '</ol></td>'
    message += '<td>'
    for name in decisionServices:
        message += '<br/>'
        message += '<a href="{}">{}</a>'.format(url_for('show_decision_service', decisionServiceName=name), name)
    message += '</td>'
    message += '</tr>'
    message += '<tr>'
    message += '<td><p>Upload your DMN compatible Excel workook here</p>'
    message += '<form id="form" action ="{}" method="post" enctype="multipart/form-data">'.format(url_for('upload_file'))
    message += '<input id="file" type="file" name="file">'
    message += '<input id="submit" type="submit" value="Upload your workbook"></p>'
    message += '</form>'
    message += '</tr>'
    message += '<td></td>'
    message += '</table>'
    message += '<p align="center"><b><a href="{}">{}</a></b></p>'.format(url_for('upload_api'), 'OpenAPI specification for Decision Central file upload')
    message += '<p><b><u>WARNING:</u></b>This is not a production service. '
    message += 'This server can be rebooted at any time. When that happens everything is lost. You will need to re-upload you DMN compliant Excel workbooks in order to restore services. '
    message += 'There is no security/login requirements on this service. Anyone can upload their rules, using a Excel workbook with the same name as yours, thus replacing/corrupting your rules. '
    message += 'It is recommended that you obtain a copy of the source code from <a href="https://github.com/russellmcdonell/DecisionCentral">GitHub</a> and run it on your own server/laptop with appropriate security.'
    message += 'This in not production ready software. It is built, using <a href="https://pypi.org/project/pyDMNrules/">pyDMNrules</a>. '
    message += 'You can build production ready solutions using <b>pyDMNrules</b>, but this is not one of those solutions.</p></body></html>'
    return message


@app.route('/uploadapi', methods=['GET'])
def upload_api():
        # Assembling and send the HTML content
        message = '<html><head><title>Decision Service file upload Open API Specification</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">Open API Specification for Decision Service file upload</h2>'
        message += '<pre>'
        openapi = mkUploadOpenAPI()
        message += openapi
        message += '</pre>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p>'.format(url_for('download_upload_api'), 'Download the OpenAPI Specification for Decision Central file upload')
        message += '<div align="center">[curl {}{}]</div>'.format(urlparse(request.base_url).hostname, url_for('download_upload_api'))
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return message


@app.route('/downloaduploadapi', methods=['GET'])
def download_upload_api():

    yaml = io.BytesIO(bytes(mkUploadOpenAPI(), 'utf-8'))

    return send_file(yaml, as_attachment=True, download_name='DecisionCentral_upload.yaml', mimetype='text/plain')


@app.route('/upload', methods=['POST'])
def upload_file():

    global decisionServices

    if 'file' not in request.files:
        message = '<html><head><title>Decision Central - No file part</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No file part found in the upload request</h2>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return Response(message, status=400)
    file = request.files['file']
    if file.filename == '':
        message = '<html><head><title>Decision Central - No filename</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No filename found in the upload request</h2>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return Response(message, status=400)
    name = secure_filename(file.filename)
    if ('.' not in name) or (name.split('.')[-1].lower() not in ALLOWED_EXTENSIONS):
        message = '<html><head><title>Decision Central - invalid file extension</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">Invalid file extension in the upload request</h2>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return Response(message, status=400)
    extn = name.split('.')[-1].lower()

    if extn in Excel_EXTENSIONS:
        name = file.filename
        decisionServiceName = name[:-5]
        workbook = io.BytesIO()                 # Somewhere to store the DMN compliant Excel workbook
        file.save(workbook)
        # Create a Decision Service from the uploaded file
        try:                # Convert file to workbook
            wb = load_workbook(filename=workbook)
        except Exception as e:
            message = '<html><head><title>Decision Central - Bad Excel workbook</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            message += '<h2 align="center">Bad Excel workbook</h2>'
            message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
            return Response(message, status=400)

        dmnRules = pyDMNrules.DMN()             # An empty Rules Engine
        status = dmnRules.use(wb)               # Add the rules from this DMN compliant Excel workbook
    else:
        name = file.filename
        decisionServiceName = name[:-4]
        xml = file.read()
        # Create a Decision Service from the uploaded file
        dmnRules = pyDMNrules.DMN()             # An empty Rules Engine
        status = dmnRules.useXML(xml)            # Add the rules from this DMN compliant XML file

    if 'errors' in status:
        message = '<html><head><title>Decision Central - Invalid DMN</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">There were Errors in your DMN rules</h2>'
        for i in range(len(status['errors'])):
            message += '<pre>{}</pre>'.format(status['errors'][i])
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return Response(message, status=400)

    # Add this decision service to the list
    decisionServices[decisionServiceName] = copy.deepcopy(dmnRules)

    # Assembling and send the HTML content
    message = '<html><head><title>Decision Central - uploaded</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
    message += '<h2 align="center">Your DMN compatible Excel workbook has been successfully uploaded</h2>'
    message += '<h3 align="center">Your Decision Service has been created</h3>'
    message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
    return Response(message, status=201)


@app.route('/show/<decisionServiceName>', methods=['GET'])
def show_decision_service(decisionServiceName):

    global decisionServices

    if decisionServiceName not in decisionServices:
        message = '<html><head><title>Decision Central - no such Decision Service</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No decision service named {}</h2>'.format(decisionServiceName)
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return message

    dmnRules = decisionServices[decisionServiceName]
    glossary = dmnRules.getGlossary()
    glossaryNames = dmnRules.getGlossaryNames()
    sheets = dmnRules.getSheets()

    # Assembling and send the HTML content
    message = '<html><head><title>Decision Service {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName)
    message += '<h2 align="center">Your Decision Service {}</h2>'.format(decisionServiceName)
    message += '<table align="center" style="font-size:120%">'
    message += '<tr>'
    message += '<th>Test Decision Service {}</th>'.format(decisionServiceName)
    message += '<th>The Decision Services {} parts</th>'.format(decisionServiceName)
    message += '</tr>'

    # Create the user input form
    message += '<td>'
    message += '<form id="form" action ="{}" method="post">'.format(url_for('decision_service', decisionServiceName=decisionServiceName))
    message += '<h5>Enter values for these Variables</h5>'
    message += '<table>'
    for concept in glossary:
        firstLine = True
        for variable in glossary[concept]:
            message += '<tr>'
            if firstLine:
                message += '<td>{}</td><td style="text-align=right">{}</td>'.format(concept, variable)
                firstLine = False
            else:
                message += '<td></td><td style="text-align=right">{}</td>'.format(variable)
            message += '<td><input type="text" name="{}" style="text-align=left"></input></td>'.format(variable)
            if len(glossaryNames) > 1:
                (FEELname, value, attributes) = glossary[concept][variable]
                if len(attributes) == 0:
                    message += '<td style="text-align=left"></td>'
                else:
                    message += '<td style="text-align=left">{}</td>'.format(attributes[0])
            message += '</tr>'
    message += '</table>'
    message += '<h5>then click the "Make a Decision" button</h5>'
    message += '<input type="submit" value="Make a Decision"/></p>'
    message += '</form>'
    message += '</td>'

    # And links for the Decision Service parts
    message += '<td style="vertical-align:top">'
    message += '<br/>'
    message += '<a href="{}">{}</a>'.format(url_for('show_decision_service_part', decisionServiceName=decisionServiceName, part='/glossary'), 'Glossary')
    message += '<br/>'
    message += '<a href="{}">{}</a>'.format(url_for('show_decision_service_part', decisionServiceName=decisionServiceName,  part='/decision'), 'Decision Table'.replace(' ', '&nbsp;'))
    for sheet in sheets:
        message += '<br/>'
        message += '<a href="{}">{}</a>'.format(url_for('show_decision_service_part', decisionServiceName=decisionServiceName,  part=sheet), sheet.replace(' ', '&nbsp;'))
    message += '<br/>'
    message += '<br/>'
    message += '<a href="{}">{}</a>'.format(url_for('show_decision_service_part', decisionServiceName=decisionServiceName,  part='/api'), 'OpenAPI specification'.replace(' ', '&nbsp;'))
    message += '<br/>'
    message += '<br/>'
    message += '<br/>'
    message += '<br/>'
    message += '<br/>'
    message += '<a href="{}">Delete the {} Decision Service</a>'.format(url_for('delete_decision_service', decisionServiceName=decisionServiceName), decisionServiceName.replace(' ', '&nbsp;'))
    message += '</td>'
    message += '</tr></table>'
    message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
    return message


@app.route('/show/<decisionServiceName>/<part>', methods=['GET'])
def show_decision_service_part(decisionServiceName, part):

    global decisionServices

    if decisionServiceName not in decisionServices:
        message = '<html><head><title>Decision Central - no such Decision Service</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No decision service named {}</h2>'.format(decisionServiceName)
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return message

    dmnRules = decisionServices[decisionServiceName]
    if part == 'glossary':          # Show the Glossary for this Decision Service
        glossaryNames = dmnRules.getGlossaryNames()
        glossary = dmnRules.getGlossary()

        # Assembling and send the HTML content
        message = '<html><head><title>Decision Service {} Glossary</title><link ref="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName)
        message += '<h2 align="center">The Glossary for the {} Decision Service</h2>'.format(decisionServiceName)
        message += '<div style="width:25%;background-color:black;color:white">{}</div>'.format('Glossary - ' + glossaryNames[0])
        message += '<table style="border-collapse:collapse;border:2px solid"><tr>'
        message += '<th style="border:2px solid;background-color:LightSteelBlue">Variable</th><th style="border:2px solid;background-color:LightSteelBlue">Business Concept</th><th style="border:2px solid;background-color:LightSteelBlue">Attribute</th>'
        if len(glossaryNames) > 1:
            for i in range(1, len(glossaryNames)):
                message += '<th style="border:2px solid;background-color:DarkSeaGreen">{}</th>'.format(glossaryNames[i])
        message += '</tr>'
        for concept in glossary:
            rowspan = len(glossary[concept].keys())
            firstRow = True
            for variable in glossary[concept]:
                message += '<tr><td style="border:2px solid">{}</td>'.format(variable)
                (FEELname, value, attributes) = glossary[concept][variable]
                dotAt = FEELname.find('.')
                if dotAt != -1:
                    FEELname = FEELname[dotAt + 1:]
                if firstRow:
                    message += '<td rowspan="{}" style="border:2px solid">{}</td>'.format(rowspan, concept)
                    firstRow = False
                message += '<td style="border:2px solid">{}</td>'.format(FEELname)
                if len(glossaryNames) > 1:
                    for i in range(len(glossaryNames) - 1):
                        if i < len(attributes):
                            message += '<td style="border:2px solid">{}</td>'.format(attributes[i])
                        else:
                            message += '<td style="border:2px solid"></td>'
                message += '</tr>'
        message += '</table>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('show_decision_service', decisionServiceName=decisionServiceName), ('Return to Decision Service ' + decisionServiceName).replace(' ','&nbsp;'))
        return message
    elif part == 'decision':            # Show the Decision for this Decision Service
        decisionName = dmnRules.getDecisionName()
        decision = dmnRules.getDecision()

        # Assembling and send the HTML content
        message = '<html><head><title>Decision Service {} Decision Table</title><link ref="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName)
        message += '<h2 align="center">The Decision Table for the {} Decision Service</h2>'.format(decisionServiceName)
        message += '<div style="width:25%;background-color:black;color:white">{}</div>'.format('Decision - ' + decisionName)
        message += '<table style="border-collapse:collapse;border:2px solid">'
        inInputs = True
        inDecide = False
        for i in range(len(decision)):
            message += '<tr>'
            for j in range(len(decision[i])):
                if i == 0:
                    if decision[i][j] == 'Decisions':
                        inInputs = False
                        inDecide = True
                    if inInputs:
                        message += '<th style="border:2px solid;background-color:DodgerBlue">{}</th>'.format(decision[i][j])
                    elif inDecide:
                        message += '<th style="border:2px solid;background-color:LightSteelBlue">{}</th>'.format(decision[i][j])
                    else:
                        message += '<th style="border:2px solid;background-color:DarkSeaGreen">{}</th>'.format(decision[i][j])
                    if decision[i][j] == 'Execute Decision Tables':
                        inDecide = False
                else:
                    if decision[i][j] == '-':
                        message += '<td align="center" style="border:2px solid">{}</td>'.format(decision[i][j])
                    else:
                        message += '<td style="border:2px solid">{}</td>'.format(decision[i][j])
            message += '</tr>'
        message += '</table>'
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('show_decision_service', decisionServiceName=decisionServiceName), ('Return to Decision Service ' + decisionServiceName).replace(' ','&nbsp;'))
        return message
    elif part == 'api':         # Show the OpenAPI definition for this Decision Service
        glossary = dmnRules.getGlossary()

        # Assembling and send the HTML content
        message = '<html><head><title>Decision Service {} Open API Specification</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName)
        message += '<h2 align="center">Open API Specification for the {} Decision Service</h2>'.format(decisionServiceName)
        message += '<pre>'
        openapi = mkOpenAPI(glossary, decisionServiceName)
        message += openapi
        message += '</pre>'
        message += '<p align="center"><b><a href="{}">{} {}</a></b></p>'.format(url_for('download_decision_service_api', decisionServiceName=decisionServiceName), 'Download the OpenAPI Specification for Decision Service', decisionServiceName)
        message += '<div align="center">[curl {}{}]</div>'.format(urlparse(request.base_url).hostname, url_for('download_decision_service_api', decisionServiceName=decisionServiceName))
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('show_decision_service', decisionServiceName=decisionServiceName), ('Return to Decision Service ' + decisionServiceName).replace(' ','&nbsp;'))
        return message
    else:                       # Show a worksheet
        sheets = dmnRules.getSheets()
        if part not in sheets:
            message = '<html><head><title>Decision Central - no such Decision Table</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            message += '<h2 align="center">No decision table named {}</h2>'.format(part)
            message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
            return message

        # Assembling and send the HTML content
        message = '<html><head><title>Decision Service {} sheet "{}"</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName, part)
        message += '<h2 align="center">The Decision sheet "{}" for Decision Service {}</h2>'.format(part, decisionServiceName)
        message += sheets[part]
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('show_decision_service', decisionServiceName=decisionServiceName), ('Return to Decision Service ' + decisionServiceName).replace(' ','&nbsp;'))
        return message


@app.route('/download/<decisionServiceName>', methods=['GET'])
def download_decision_service_api(decisionServiceName):
    if decisionServiceName not in decisionServices:
        message = '<html><head><title>Decision Central - no such Decision Service</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No decision service named {}</h2>'.format(decisionServiceName)
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return message

    dmnRules = decisionServices[decisionServiceName]

    dmnRules = decisionServices[decisionServiceName]
    glossary = dmnRules.getGlossary()
    yaml = io.BytesIO(bytes(mkOpenAPI(glossary, decisionServiceName), 'utf-8'))

    return send_file(yaml, as_attachment=True, download_name=decisionServiceName + '.yaml', mimetype='text/plain')


@app.route('/delete/<decisionServiceName>', methods=['GET'])
def delete_decision_service(decisionServiceName):

    global decisionServices

    if decisionServiceName not in decisionServices:
        message = '<html><head><title>Decision Central - no such Decision Service</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
        message += '<h2 align="center">No decision service named {}</h2>'.format(decisionServiceName)
        message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
        return message

    del decisionServices[decisionServiceName]
    message = '<html><head><title>Decision Central - delete</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
    message += '<h3 align="center">Decision Service {} has been deleted</h3>'.format(decisionServiceName)
    message += '<p align="center"><b><a href="/">{}</a></b></p></body></html>'.format('Return to Decision Central')
    return message


@app.route('/api/<decisionServiceName>', methods=['POST'])
def decision_service(decisionServiceName):

    global decisionServices

    if decisionServiceName not in decisionServices:
        if request.content_type == 'application/x-www-form-urlencoded':         # From the web page
            message = '<html><head><title>Decision Central - no such Decision Service</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            message += '<h2 align="center">No decision service named {}</h2>'.format(decisionServiceName)
            message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
            return message
        else:
            abort(400)
    dmnRules = decisionServices[decisionServiceName]

    data = {}
    if request.content_type == 'application/x-www-form-urlencoded':         # From the web page
        for variable in request.form:
            value = request.form[variable].strip()
            data[variable] = convertIn(value)
    else:
        data = request.get_json()
        for variable in data:
            value = data[variable]
            data[variable] = convertIn(value)

    # Check if JSON or HTML response required
    wantsJSON = False
    for i in range(len(request.accept_mimetypes)):
        (mimeType, quality) = request.accept_mimetypes[i]
        if mimeType == 'application/json':
            wantsJSON = True

    # Now make the decision
    (status, newData) = dmnRules.decide(data)
    if 'errors' in status:
        if request.content_type == 'application/x-www-form-urlencoded':         # From the web page
            message = '<html><head><title>Decision Central - bad status from Decision Service {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(decisionServiceName)
            message += '<h2 align="center">Your Decision Service {} returned a bad status</h2>'.format(decisionServiceName)
            for i in range(len(status['errors'])):
                message += '<pre>{}</pre>'.format(status['errors'][i])
            message += '<p align="center"><b><a href="{}">{}</a></b></p></body></html>'.format(url_for('splash'), 'Return to Decision Central')
            return message
        else:
            newData = {}
            newData['Result'] = {}
            newData['Executed Rule'] = []
            newData['Status'] = status
            return jsonify(newData)

    if wantsJSON:
        # Return the results dictionary
        # The structure of the returned data varies depending upon the Hit Policy of the last executed Decision Table
        # We don't have the Hit Policy, but we can work it out
        returnData = {}
        if isinstance(newData, list):
            newData = newData[-1]
        returnData['Result'] = {}
        for variable in newData['Result']:
            value = newData['Result'][variable]
            if isinstance(value, dict):
                returnData['Result'][variable] = {}
                for key in value:
                    returnData['Result'][variable][key] = convertOut(value[j])
            elif isinstance(value, list):         # The last executed Decision Table was a COLLECTION
                returnData['Result'][variable] = []
                for j in range(len(value)):
                    returnData['Result'][variable].append(convertOut(value[j]))
            else:
                returnData['Result'][variable] = convertOut(value)
        returnData['Executed Rule'] = []
        if isinstance(newData['Executed Rule'], list):           # The last executed Decision Table was RULE ORDER, OUTPUT ORDER or COLLECTION
            for i in range(len(newData['Executed Rule'])):
                returnData['Executed Rule'].append([])
                (executedDecision, decisionTable,ruleId) = newData['Executed Rule'][i]
                returnData['Executed Rule'][-1].append(executedDecision)
                returnData['Executed Rule'][-1].append(decisionTable)
                returnData['Executed Rule'][-1].append(ruleId)
        else:
            (executedDecision, decisionTable,ruleId) = newData['Executed Rule']
            returnData['Executed Rule'].append(executedDecision)
            returnData['Executed Rule'].append(decisionTable)
            returnData['Executed Rule'].append(ruleId)
        returnData['Status'] = status
        return jsonify(returnData)
    else:
        # Assembling the HTML content
        message = '<html><head><title>The decision from Decision Service {}</title><link rel="icon" href="data:,"></head><body>'.format(decisionServiceName)
        message += '<h1>Decision Service {}</h1>'.format(decisionServiceName)
        message += '<h2>The Decision</h2>'
        message += '<table style="width:70%">'
        message += '<tr><th style="border:2px solid">Variable</th>'
        message += '<th style="border:2px solid">Value</th></tr>'
        if isinstance(newData, list):
            newData = newData[-1]
        for variable in newData['Result']:
            if newData['Result'][variable] == '':
                continue
            message += '<tr><td style="border:2px solid">{}</td>'.format(variable)
            message += '<td style="border:2px solid">{}</td></tr>'.format(str(newData['Result'][variable]))
        message += '</table>'
        message += '<h2>The Deciders</h2>'
        message += '<table style="width:70%">'
        message += '<tr><th style="border:2px solid">Executed Decision</th>'
        message += '<th style="border:2px solid">Decision Table</th>'
        message += '<th style="border:2px solid">Rule Id</th></tr>'
        if isinstance(newData['Executed Rule'], list):           # The last executed Decision Table was RULE ORDER, OUTPUT ORDER or COLLECTION
            for j in range(len(newData['Executed Rule'])):
                (executedDecision, decisionTable,ruleId) = newData['Executed Rule'][j]
                message += '<tr><td style="border:2px solid">{}</td>'.format(executedDecision)
                message += '<td style="border:2px solid">{}</td>'.format(decisionTable)
                message += '<td style="border:2px solid">{}</td></tr>'.format(ruleId)
                message += '<tr>'
        else:
            (executedDecision, decisionTable,ruleId) = newData['Executed Rule']
            message += '<tr><td style="border:2px solid">{}</td>'.format(executedDecision)
            message += '<td style="border:2px solid">{}</td>'.format(decisionTable)
            message += '<td style="border:2px solid">{}</td></tr>'.format(ruleId)
            message += '<tr>'
        message += '</table>'
        message += '<p align="center"><b><a href="/">{}</a></b></p></body></html>'.format('Return to Decision Central')
        return message

if __name__ == '__main__':
    app.run(host="0.0.0.0")
