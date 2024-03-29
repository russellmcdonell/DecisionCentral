#!/usr/bin/env python

'''
A script to build a web site as a central repository for DMN decision service.

SYNOPSIS
$ python DecisionCentral.py [-v loggingLevel|--verbose=logingLevel] [-L logDir|--logDir=logDir] [-l logfile|--logfile=logfile] [-p portNo|--port=portNo]

REQUIRED


OPTIONS
-v loggingLevel|--verbose=loggingLevel
Set the level of logging that you want (defaut INFO).

-L logDir
The directory where the log file will be written.

-l logfile|--logfile=logfile
The name of a logging file where you want all messages captured.

-p portNo|--port=portNo
The port used for listening for http requests


This script lets users upload Excel workbooks or XML files, which must comply to the DMN standard.
Once an Excel workbook or XML file has been uploaded and parsed successfully as DMN cmopliant, this script will
1. Create a dedicated web page so that the user can interactively run/check their decision service
2. Create an API so that the user can use, programatically, their decision service
3. Create an OpenAPI yaml file documenting the created API

'''

# Import all the modules that make life easy
import sys
import os
import io
import argparse
import logging
import copy
import pySFeel
from pySFeel import SFeelLexer
import re
import csv
import ast
import json
import datetime
import dateutil.parser, dateutil.tz
import pyDMNrules
import threading
from werkzeug.utils import secure_filename
from urllib.parse import urlparse, urlencode, parse_qs, quote, unquote
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import parse_headers
from http import client
from socketserver import ThreadingMixIn
from openpyxl import load_workbook

# This next section is plagurised from /usr/include/sysexits.h
EX_OK = 0        # successful termination
EX_WARN = 1        # non-fatal termination with warnings

EX_USAGE = 64        # command line usage error
EX_DATAERR = 65        # data format error
EX_NOINPUT = 66        # cannot open input
EX_NOUSER = 67        # addressee unknown
EX_NOHOST = 68        # host name unknown
EX_UNAVAILABLE = 69    # service unavailable
EX_SOFTWARE = 70    # internal software error
EX_OSERR = 71        # system error (e.g., can't fork)
EX_OSFILE = 72        # critical OS file missing
EX_CANTCREAT = 73    # can't create (user) output file
EX_IOERR = 74        # input/output error
EX_TEMPFAIL = 75    # temp failure; user is invited to retry
EX_PROTOCOL = 76    # remote error in protocol
EX_NOPERM = 77        # permission denied
EX_CONFIG = 78        # configuration error


class DecisionCentralData:
    '''
The Decision Central Data - required for threading
    '''

    def __init__(self, progName):
        self.lexer = pySFeel.SFeelLexer()
        self.parser = pySFeel.SFeelParser()
        self.logger = logging.getLogger('DecisionCentral')
        self.logger.propagate = True
        self.logfmt = progName + ' %(threadName)s [%(asctime)s]: %(message)s'
        self.formatter = logging.Formatter(fmt=self.logfmt, datefmt='%d/%m/%y %H:%M:%S %p')
        for hdlr in self.logger.handlers:
            hdlr.setFormatter(self.formatter)
        return


# The command line arguments and their related globals
logDir = '.'                # The directory where the log files will be written
logging_levels = {0:logging.CRITICAL, 1:logging.ERROR, 2:logging.WARNING, 3:logging.INFO, 4:logging.DEBUG}
loggingLevel = logging.NOTSET        # The default logging level
logFile = None               # The name of the logfile (output to stderr if None)
fh = None                    # The logging handler for file things
sh = None                    # The logging handler for stdin things
decisionServices = {}        # The dictionary of currently defined Decision services
Excel_EXTENSIONS = {'xlsx', 'xlsm'}
ALLOWED_EXTENSIONS = {'xlsx', 'xlsm', 'xml', 'dmn'}



# Create the class for handline http requests
class decisionCentralHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):

        return


    def convertAtString(self, thisString):
        # Convert an @string
        (status, newValue) = self.data.parser.sFeelParse(thisString[2:-1])
        if 'errors' in status:
            return thisString
        else:
            return newValue


    def convertInWeb(self, thisValue):
        # Convert a value (string) from the web form
        if not isinstance(thisValue, str):
            return thisValue
        try:
            newValue = ast.literal_eval(thisValue)
        except:
            newValue = thisValue
        return self.convertIn(newValue)


    def convertIn(self, newValue):
        if isinstance(newValue, dict):
            for key in newValue:
                if isinstance(newValue[key], int):
                    newValue[key] = float(newValue[key])
                elif isinstance(newValue[key], str) and (newValue[key][0:2] == '@"') and (newValue[key][-1] == '"'):
                    newValue[key] = self.convertAtString(newValue[key])
                elif isinstance(newValue[key], dict) or isinstance(newValue[key], list):
                    newValue[key] = self.convertIn(newValue[key])
        elif isinstance(newValue, list):
            for i in range(len(newValue)):
                if isinstance(newValue[i], int):
                    newValue[i] = float(newValue[i])
                elif isinstance(newValue[i], str) and (newValue[i][0:2] == '@"') and (newValue[i][-1] == '"'):
                    newValue[i] = self.convertAtString(newValue[i])
                elif isinstance(newValue[i], dict) or isinstance(newValue[i], list):
                    newValue[i] = self.convertIn(newValue[i])
        elif isinstance(newValue, str) and (newValue[0:2] == '@"') and (newValue[-1] == '"'):
            newValue = self.convertAtString(newValue)
        return newValue


    def convertOut(self, thisValue):
        if isinstance(thisValue, datetime.date):
            return '@"' + thisValue.isoformat() +'"'
        elif isinstance(thisValue, datetime.datetime):
            return '@"' + thisValue.isoformat(sep='T') +'"'
        elif isinstance(thisValue, datetime.time):
            return '@"' + thisValue.isoformat() + '"'
        elif isinstance(thisValue, datetime.timedelta):
            sign = ''
            duration = thisValue.total_seconds()
            if duration < 0:
                sign = '-'
                duration = -duration
            secs = duration % 60
            duration = int(duration / 60)
            mins = duration % 60
            duration = int(duration / 60)
            hours = duration % 24
            days = int(duration / 24)
            return '@"%sP%dDT%dH%dM%fS"' % (sign, days, hours, mins, secs)
        elif isinstance(thisValue, bool):
            if thisValue:
                return 'true'
            else:
                return 'false'
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
                thisValue[item] = self.convertOut(thisValue[item])
            return thisValue
        elif isinstance(thisValue, list):
            for i in range(len(thisValue)):
                thisValue[i] = self.convertOut(thisValue[i])
            return thisValue
        else:
            return thisValue


    def mkOpenAPI(self, glossary, name, sheet):
        thisAPI = []
        thisAPI.append('openapi: 3.0.0')
        thisAPI.append('info:')
        if sheet is None:
            thisAPI.append('  title: Decision Service {}'.format(name))
        else:
            thisAPI.append('  title: Decision Service {} - Decision Table {}'.format(name, sheet))
        thisAPI.append('  version: 1.0.0')
        if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}://{}"'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host']))
            thisAPI.append('  ]')
        elif 'Host' in self.headers:
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}"'.format(self.headers['Host']))
            thisAPI.append('  ]')
        elif 'Forwarded' in self.headers:
            forwards = self.headers['Forwarded'].split(';')
            origin = forwards[0].split('=')[1]
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}"'.format(origin))
            thisAPI.append('  ]')
        thisAPI.append('paths:')
        if sheet is None:
            thisAPI.append('  /api/{}:'.format(quote(name)))
        else:
            thisAPI.append('  /api/{}_table/{}:'.format(quote(name), quote(sheet)))
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
            if concept != 'Data':
                thisAPI.append('        "{}":'.format(concept))
                thisAPI.append('          type: array')
                thisAPI.append('          items:')
                thisAPI.append('            type: object')
                thisAPI.append('            properties:')
                for variable in glossary[concept]:
                    thisAPI.append('              "{}":'.format(variable[len(concept)+1:]))
                    thisAPI.append('                type: string')
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


    def mkUploadOpenAPI(self):
        thisAPI = []
        thisAPI.append('openapi: 3.0.0')
        thisAPI.append('info:')
        thisAPI.append('  title: Decision Service file upload API')
        thisAPI.append('  version: 1.0.0')
        if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}://{}"'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host']))
            thisAPI.append('  ]')
        elif 'Host' in self.headers:
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}"'.format(self.headers['Host']))
            thisAPI.append('  ]')
        elif 'Forwarded' in self.headers:
            forwards = self.headers['Forwarded'].split(';')
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


    def mkDeleteOpenAPI(self, name):
        thisAPI = []
        thisAPI.append('openapi: 3.0.0')
        thisAPI.append('info:')
        thisAPI.append('  title: Delete Decision Service API')
        thisAPI.append('  version: 1.0.0')
        if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}://{}"'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host']))
            thisAPI.append('  ]')
        elif 'Host' in self.headers:
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}"'.format(self.headers['Host']))
            thisAPI.append('  ]')
        elif 'Forwarded' in self.headers:
            forwards = self.headers['Forwarded'].split(';')
            origin = forwards[0].split('=')[1]
            thisAPI.append('servers:')
            thisAPI.append('  [')
            thisAPI.append('    "url":"{}"'.format(origin))
            thisAPI.append('  ]')
        thisAPI.append('paths:')
        thisAPI.append('  /delete/{}:'.format(quote(name)))
        thisAPI.append('    get:')
        thisAPI.append('      summary: Delete a DecisionCentral Decision Service')
        thisAPI.append('      operationId: delete')
        thisAPI.append('      responses:')
        thisAPI.append('        200:')
        thisAPI.append('          description: Item deleted')
        thisAPI.append('          content:')
        thisAPI.append('            text/html:')
        thisAPI.append('              schema:')
        thisAPI.append('                type: string')
        thisAPI.append('        400:')
        thisAPI.append('          description: Invalid request')
        return '\n'.join(thisAPI)


    def do_GET(self):

        global decisionServices

        # Supported URLs are
        # / - the splash page and list of already created decision services
        # /show/decisionServiceName - The User Interface, plus a link to the OpenAPI YAML specification of the API, plus a list of the decision parts
        # /show/decisionServiceName/part - one of the parts of the decision service - glossary/decision/api/one of the sheets
        # /download/decisionServiceName - download the OPEN API YAML specification for this decision service
        # /delete/decisionServiceName - delete this decision service

        # Reset all the globals
        self.data = DecisionCentralData('[desisionCentral-' + threading.current_thread().name + ']')

        # Parse the URl
        request = urlparse(self.path)
        # Start the response
        if request.path == '/':         # The splash page
            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Assembling and send the HTML content
            self.data.logger.info('GET {}'.format(self.path))
            self.message = '<html><head><title>Decision Central</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            self.message += '<h1 style="text-align:center">Welcolme to Decision Central</h1>'
            self.message += '<h3 style="text-align:center">Your home for all your DMN Decision Services</h3>'
            self.message += '<div style="text-align:center;margin:auto"><b>Here you can create a Decision Service by simply'
            self.message += '<br/>uploading a DMN compatible Excel workbook or DMN compliant XML file</b></div>'
            self.message += '<br/><table width="90%" style="text-align:left;margin:auto;font-size:120%">'
            self.message += '<tr>'
            self.message += '<th style="padding-left:3ch">With each created Decision Service you get</th>'
            self.message += '<th>Available Decision Services</th>'
            self.message += '</tr>'
            self.message += '<tr><td>'
            self.message += '<ol>'
            self.message += '<li>An API which you can use to test integration to you Decision Service'
            self.message += '<li>A user interface where you can perform simple tests of your Decision Service'
            self.message += '<li>A list of links to HTML renditions of the Decision Tables in your Decision Service'
            self.message += '<li>A link to the Open API YAML file which describes you Decision Service'
            self.message += '</ol></td>'
            self.message += '<td>'
            for name in decisionServices:
                self.message += '<br/>'
                self.message += '<a href="{}">{}</a>'.format(self.path + 'show/' + name, name.replace(' ', '&nbsp;'))
            self.message += '</td>'
            self.message += '</tr>'
            self.message += '<tr>'
            self.message += '<td><p>Upload your DMN compatible Excel workook or DMN compliant XML file here</p>'
            self.message += '<form id="form" action ="{}" method="post" enctype="multipart/form-data">'.format(self.path + 'upload')
            self.message += '<input id="file" type="file" name="file">'
            self.message += '<input id="submit" type="submit" value="Upload your workbook or XML file"></p>'
            self.message += '</form>'
            self.message += '</tr>'
            self.message += '<td></td>'
            self.message += '</table>'
            self.message += '<p style="text-align:center"><b><a href="{}">{}</a></b></p>'.format(self.path + 'uploadapi', 'OpenAPI Specification for Decision Central file upload')
            self.message += '<p><b><u>WARNING:</u></b>This is not a production service. '
            self.message += 'This server can be rebooted at any time. When that happens everything is lost. You will need to re-upload you DMN compliant Excel workbooks and DMN conformant XML files in order to restore services. '
            self.message += 'There is no security/login requirements on this service. Anyone can upload their rules, using a Excel workbook or XML file with the same name as yours, thus replacing/corrupting your rules. '
            self.message += 'It is recommended that you obtain a copy of the source code from <a href="https://github.com/russellmcdonell/DecisionCentral">GitHub</a> and run it on your own server/laptop with appropriate security.'
            self.message += 'This in not production ready software. It is built, using <a href="https://pypi.org/project/pyDMNrules/">pyDMNrules</a>. '
            self.message += 'You can build production ready solutions using <b>pyDMNrules</b>, but this is not one of those solutions.</p>'
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))
            return
        elif request.path == '/uploadapi':         # The file upload OpenAPI Specification
            self.data.logger.info('GET {}'.format(self.path))
            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Assembling and send the HTML content
            self.data.logger.info('GET {}'.format(self.path))
            self.message = '<html><head><title>Decision Central</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            self.message += '<h2 style="text-align:center">Open API Specification for Decision Service file upload</h2>'
            self.message += '<pre>'
            openapi = self.mkUploadOpenAPI()
            self.message += openapi
            self.message += '</pre>'
            self.message += '<p style="text-align:center"><b><a href="{}">{}</a></b></p>'.format('/downloaduploadapi', 'Download the OpenAPI Specification for Decision Central file upload')
            self.message += '<div style="text-align:center;margin:auto">[curl '
            if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
                self.message += '{}://{}'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host'])
            elif 'Host' in self.headers:
                self.message += '{}'.format(self.headers['Host'])
            elif 'Forwarded' in self.headers:
                forwards = self.headers['Forwarded'].split(';')
                origin = forwards[0].split('=')[1]
                self.message += '{}'.format(origin)
            self.message += '/downloaduploadapi]'
            self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))
        elif request.path == '/downloaduploadapi':         # Download the file upload OpenAPI Specification
            self.data.logger.info('GET {}'.format(self.path))
            openapi = self.mkUploadOpenAPI()

            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Disposition', 'attachement; filename="DecisionCentral_upload.yaml"')
            self.end_headers()
            self.wfile.write(openapi.encode('utf-8'))
            return
        elif request.path[0:6] == '/show/':         # Show Decision Service or Decision Service Part
            self.data.logger.info('GET {}'.format(self.path))
            name = unquote(request.path[6:])
            self.data.logger.info('GET - name {}'.format(name))
            if name in decisionServices:            # Show a Decision Service - an form for input data and the parts of the decision service
                dmnRules = decisionServices[name]
                self.data.logger.info('GET - type(dmnRules) {}'.format(type(dmnRules)))
                glossaryNames = dmnRules.getGlossaryNames()
                self.data.logger.info('GET - glossaryNames {}'.format(glossaryNames))
                glossary = dmnRules.getGlossary()
                self.data.logger.info('GET - glossary {}'.format(glossary))
                sheets = dmnRules.getSheets()
                self.data.logger.info('GET - sheets {}'.format(sheets))

                # Output the web page
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()

                # Assembling and send the HTML content
                self.message = '<html><head><title>Decision Service {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                self.message += '<h2 style="text-align:center">Your Decision Service {}</h2>'.format(name)
                self.message += '<table style="text-align:left;margin:auto;font-size:120%">'
                self.message += '<tr>'
                self.message += '<th>Test Decision Service {}</th>'.format(name)
                self.message += '<th>The Decision Services {} parts</th>'.format(name)
                self.message += '</tr>'

                # Create the user input form
                self.message += '<td>'
                self.message += '<form id="form" action ="{}" method="post">'.format('/api/' + quote(name))
                self.message += '<h5>Enter values for these Variables</h5>'
                self.message += '<table style="border-spacing:0">'
                for concept in glossary:
                    if concept != 'Data':
                        self.message += '<tr><td>{}</td>'.format(concept)
                        self.message += '<td colspan="3"><input type="text" name="{}" style="text-align:left;width:100%"></input></td></tr>'.format(concept)
                    for variable in glossary[concept]:
                        self.message += '<tr>'
                        self.message += '<td></td><td style="text-align:right">{}</td>'.format(variable)
                        self.message += '<td><input type="text" name="{}" style="text-align:left"></input></td>'.format(variable)
                        if len(glossaryNames) > 1:
                            (FEELname, value, attributes) = glossary[concept][variable]
                            if len(attributes) == 0:
                                self.message += '<td style="text-align:left"></td>'
                            else:
                                self.message += '<td style="text-align:left">{}</td>'.format(attributes[0])
                        self.message += '</tr>'
                self.message += '</table>'
                self.message += '<h5>then click the "Make a Decision" button</h5>'
                self.message += '<input type="submit" value="Make a Decision"/></p>'
                self.message += '</form>'
                self.message += '</td>'

                # And links for the Decision Service parts
                self.message += '<td style="vertical-align:top">'
                self.message += '<br/>'
                self.message += '<a href="{}">{}</a>'.format(self.path + '/glossary', 'Glossary')
                self.message += '<br/>'
                self.message += '<a href="{}">{}</a>'.format(self.path + '/decision', 'Decision Table'.replace(' ', '&nbsp;'))
                for sheet in sheets:
                    self.message += '<br/>'
                    self.message += '<a href="{}">{}</a>'.format(self.path + '/' + sheet, sheet.replace(' ', '&nbsp;'))
                self.message += '<br/>'
                self.message += '<br/>'
                self.message += '<a href="{}">{}</a>'.format(self.path + '/api', 'OpenAPI specification'.replace(' ', '&nbsp;'))
                self.message += '<br/>'
                self.message += '<br/>'
                self.message += '<br/>'
                self.message += '<br/>'
                self.message += '<br/>'
                self.message += '<a href="/delete/{}">Delete the {} Decision Service</a>'.format(quote(name), name.replace(' ', '&nbsp;'))
                self.message += '<br/>'
                self.message += '<a href="/show_delete/{}">API for deleting the {} Decision Service</a>'.format(quote(name), name.replace(' ', '&nbsp;'))
                self.message += '</td>'
                self.message += '</tr></table>'
                self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                self.message += '</body></html>'
                self.wfile.write(self.message.encode('utf-8'))
                return
            else:                           # Check for /show/DecisionServiceName/part
                bits = name.split('/')
                self.data.logger.info('GET - bits {}'.format(bits))
                if len(bits) != 2:
                    self.data.logger.warning('Bad path - {}'.format(self.path))
                    self.send_error(400)
                    return
                name = bits[0]
                if name not in decisionServices:                # Check that we have this Decision Service
                    # Return Bad Request
                    self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                    self.send_error(400)
                    return
                part = bits[1]                      # The part to show
                dmnRules = decisionServices[name]
                if part == 'glossary':          # Show the Glossary for this Decision Service
                    glossaryNames = dmnRules.getGlossaryNames()
                    glossary = dmnRules.getGlossary()
                    # Output the web page for the Glossary
                    # dict:{keys:Business Concept names, value:dict{keys:Variable names, value:tuple(FEELname, current value)}}
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Assembling and send the HTML content
                    self.message = '<html><head><title>Decision Service {} Glossary</title><link ref="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                    self.message += '<h2 style="text-align:center">The Glossary for the {} Decision Service</h2>'.format(name)
                    self.message += '<div style="width:25%;background-color:black;color:white">{}</div>'.format('Glossary - ' + glossaryNames[0])
                    self.message += '<table style="border-collapse:collapse;border:2px solid"><tr>'
                    self.message += '<th style="border:2px solid;background-color:LightSteelBlue">Variable</th><th style="border:2px solid;background-color:LightSteelBlue">Business Concept</th><th style="border:2px solid;background-color:LightSteelBlue">Attribute</th>'
                    if len(glossaryNames) > 1:
                        for i in range(len(glossaryNames)):
                            self.message += '<th style="border:2px solid;background-color:DarkSeaGreen">{}</th>'.format(glossaryNames[i])
                    for concept in glossary:
                        rowspan = len(glossary[concept].keys())
                        firstRow = True
                        for variable in glossary[concept]:
                            self.message += '<tr><td style="border:2px solid">{}</td>'.format(variable)
                            (FEELname, value, attributes) = glossary[concept][variable]
                            dotAt = FEELname.find('.')
                            if dotAt != -1:
                                FEELname = FEELname[dotAt + 1:]
                            if firstRow:
                                self.message += '<td rowspan="{}" style="border:2px solid">{}</td>'.format(rowspan, concept)
                                firstRow = False
                            self.message += '<td style="border:2px solid">{}</td>'.format(FEELname)
                            if len(glossaryNames) > 1:
                                for i in range(len(glossaryNames) - 1):
                                    if i < len(attributes):
                                        self.message += '<td style="border:2px solid">{}</td>'.format(attributes[i])
                                    else:
                                        self.message += '<td style="border:2px solid"></td>'
                            self.message += '</tr>'
                    self.message += '</table>'
                    self.message += '</body></html>'
                    self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
                    self.message += '</body></html>'
                    self.wfile.write(self.message.encode('utf-8'))
                    return
                elif part == 'decision':            # Show the Decision for this Decision Service
                    decisionName = dmnRules.getDecisionName()
                    self.data.logger.info('GET - decisionName {}'.format(decisionName))
                    decision = dmnRules.getDecision()
                    self.data.logger.info('GET - decision {}'.format(decision))
                    # Output the web page
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Assembling and send the HTML content
                    self.message = '<html><head><title>Decision Service {} Decision Table</title><link ref="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                    self.message += '<h2 style="text-align:center">The Decision Table for the {} Decision Service</h2>'.format(name)
                    self.message += '<div style="width:25%;background-color:black;color:white">{}</div>'.format('Decision - ' + decisionName)
                    self.message += '<table style="border-collapse:collapse;border:2px solid">'
                    inInputs = True
                    inDecide = False
                    for i in range(len(decision)):
                        self.message += '<tr>'
                        for j in range(len(decision[i])):
                            if i == 0:
                                if decision[i][j] == 'Decisions':
                                    inInputs = False
                                    inDecide = True
                                if inInputs:
                                    self.message += '<th style="border:2px solid;background-color:DodgerBlue">{}</th>'.format(decision[i][j])
                                elif inDecide:
                                    self.message += '<th style="border:2px solid;background-color:LightSteelBlue">{}</th>'.format(decision[i][j])
                                else:
                                    self.message += '<th style="border:2px solid;background-color:DarkSeaGreen">{}</th>'.format(decision[i][j])
                                if decision[i][j] == 'Execute Decision Tables':
                                    inDecide = False
                            else:
                                if decision[i][j] == '-':
                                    self.message += '<td style="text-align:center;border:2px solid">{}</td>'.format(decision[i][j])
                                else:
                                    self.message += '<td style="border:2px solid">{}</td>'.format(decision[i][j])
                        self.message += '</tr>'
                    self.message += '</table>'
                    self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
                    self.message += '</body></html>'
                    self.wfile.write(self.message.encode('utf-8'))
                    return
                elif part == 'api':         # Show the OpenAPI definition for this Decision Service
                    glossary = dmnRules.getGlossary()
                    # Output the web page
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Assembling and send the HTML content
                    self.message = '<html><head><title>Decision Service {} Open API Specification</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                    self.message += '<h2 style="text-align:center">Open API Specification for the {} Decision Service</h2>'.format(name)
                    self.message += '<pre>'
                    openapi = self.mkOpenAPI(glossary, name, None)
                    self.message += openapi
                    self.message += '</pre>'
                    self.message += '<p style="text-align:center"><b><a href="/download/{}">{} {}</a></b></p>'.format(name, 'Download the OpenAPI Specification for Decision Service', name)
                    self.message += '<div style="text-align:center;margin:auto">[curl '
                    if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
                        self.message += '{}://{}'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host'])
                    elif 'Host' in self.headers:
                        self.message += '{}'.format(self.headers['Host'])
                    elif 'Forwarded' in self.headers:
                        forwards = self.headers['Forwarded'].split(';')
                        origin = forwards[0].split('=')[1]
                        self.message += '{}'.format(origin)
                    self.message += '/download/{}]</div>'.format(quote(name))
                    self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
                    self.message += '</body></html>'
                    self.wfile.write(self.message.encode('utf-8'))
                    return
                else:                       # Show a worksheet
                    sheets = dmnRules.getSheets()
                    if part not in sheets:
                        self.data.logger.warning('GET: {} not in sheets'.format(part))
                        self.send_error(400)
                        return
                    # Output the web page
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Assembling and send the HTML content
                    self.message = '<html><head><title>Decision Service {} sheet "{}"</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name, part)
                    self.message += '<h2 style="text-align:center">The Decision sheet "{}" for Decision Service {}</h2>'.format(part, name)
                    self.message += sheets[part]
                    self.message += '<br/>'

                    # Create the user input form
                    self.message += '<form id="form" action ="/api/{}_table/{}" method="post">'.format(quote(name) , quote(part))
                    self.message += '<h5>Enter values for these Variables</h5>'
                    self.message += '<table>'
                    glossaryNames = dmnRules.getGlossaryNames()
                    glossary = dmnRules.getTableGlossary(part)
                    for concept in glossary:
                        firstLine = True
                        for variable in glossary[concept]:
                            self.message += '<tr>'
                            if firstLine:
                                self.message += '<td>{}</td><td style="text-align:right">{}</td>'.format(concept, variable)
                                firstLine = False
                            else:
                                self.message += '<td></td><td style="text-align:right">{}</td>'.format(variable)
                            self.message += '<td><input type="text" name="{}" style="text-align:left"></input></td>'.format(variable)
                            if len(glossaryNames) > 1:
                                (FEELname, variable, attributes) = glossary[concept][variable]
                                if len(attributes) == 0:
                                    self.message += '<td style="text-align:left"></td>'
                                else:
                                    self.message += '<td style="text-align:left">{}</td>'.format(attributes[0])
                            self.message += '</tr>'
                    self.message += '</table>'
                    self.message += '<h5>then click the "Make a Decision" button</h5>'
                    self.message += '<input type="submit" value="Make a Decision"/></p>'
                    self.message += '</form>'

                    self.message += '<p style="text-align:center"><b><a href="{}">{}</a></b></p>'.format('/show_api/' + quote(name) + '/' + quote(part), 'OpenAPI specification'.replace(' ', '&nbsp;'))
                    self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
                    self.message += '</body></html>'
                    self.wfile.write(self.message.encode('utf-8'))
                    return
        elif request.path[0:10] == '/show_api/':         # Show Decision Service Decision Table API
            self.data.logger.info('GET {}'.format(self.path))
            parts = unquote(request.path[10:])
            bits = parts.split('/')
            if len(bits) != 2:
                # Return Bad Request
                self.data.logger.warning('GET: {} is not a valid decisionService/decisionTable'.format(parts))
                self.send_error(400)
                return
            name = bits[0]
            part = bits[1]
            if name not in decisionServices:                # Check that we have this Decision Service
                # Return Bad Request
                self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                self.send_error(400)
                return

            dmnRules = decisionServices[name]
            sheets = dmnRules.getSheets()
            if part not in sheets:
                self.data.logger.warning('GET: {} not in sheets'.format(part))
                self.send_error(400)
                return
            glossary = dmnRules.getTableGlossary(part)

            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Assembling and send the HTML content
            self.message = '<html><head><title>Decision Service {} Open API Specification for {} Decision Table</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name, part)
            self.message += '<h2 style="text-align:center">Open API Specification for the Decision Table {} in the Decision Service {}</h2>'.format(part, name)
            self.message += '<pre>'
            openapi = self.mkOpenAPI(glossary, name, part)
            self.message += openapi
            self.message += '</pre>'
            self.message += '<p style="text-align:center"><b><a href="/download/{}/{}">Download the OpenAPI Specification for Decision Table {} in Decision Service {}</a></b></p>'.format(quote(name), quote(part), part, name)
            self.message += '<div style="text-align:center;margin:auto">[curl '
            if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
                self.message += '{}://{}'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host'])
            elif 'Host' in self.headers:
                self.message += '{}'.format(self.headers['Host'])
            elif 'Forwarded' in self.headers:
                forwards = self.headers['Forwarded'].split(';')
                origin = forwards[0].split('=')[1]
                self.message += '{}'.format(origin)
            self.message += '/download/{}/{}]</div>'.format(quote(name), quote(part))
            self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))
            return
            
        elif request.path[0:13] == '/show_delete/':         # Show Delete Decision Service API
            self.data.logger.info('GET {}'.format(self.path))
            name = unquote(request.path[13:])
            self.data.logger.info('GET - name {}'.format(name))
            if name not in decisionServices:                # Check that we have this Decision Service
                # Return Bad Request
                self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                self.send_error(400)
                return

            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Assembling and send the HTML content
            self.message = '<html><head><title>Delete Decision Service {} Open API Specification</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name.replace(' ', '&nbsp;'))
            self.message += '<h2 style="text-align:center">Open API Specification for deleting the {} Decision Service</h2>'.format(name.replace(' ', '&nbsp;'))
            self.message += '<pre>'
            openapi = self.mkDeleteOpenAPI(name)
            self.message += openapi
            self.message += '</pre>'
            self.message += '<p style="text-align:center"><b><a href="/download_delete/{}">Download the OpenAPI Specification for deleting the {} Decision Service</a></b></p>'.format(quote(name), name.replace(' ', '&nbsp;'))
            self.message += '<div style="text-align:center;margin:auto">[curl '
            if ('X-Forwarded-Host' in self.headers) and ('X-Forwarded-Proto' in self.headers):
                self.message += '{}://{}'.format(self.headers['X-Forwarded-Proto'], self.headers['X-Forwarded-Host'])
            elif 'Host' in self.headers:
                self.message += '{}'.format(self.headers['Host'])
            elif 'Forwarded' in self.headers:
                forwards = self.headers['Forwarded'].split(';')
                origin = forwards[0].split('=')[1]
                self.message += '{}'.format(origin)
            self.message += '/download_delete/{}]'.format(quote(name))
            self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))
            return
        elif request.path[0:10] == '/download/':         # Download the Open API specification
            self.data.logger.info('GET {}'.format(self.path))
            parts = unquote(request.path[10:])
            bits = parts.split('/')
            if len(bits) > 2:
                # Return Bad Request
                self.data.logger.warning('GET: {} is not a valid decisionService[/decisionTable]'.format(parts))
                self.send_error(400)
                return
            name = bits[0]
            self.data.logger.debug('GET - name {}'.format(name))
            if name not in decisionServices:                # Check that we have this Decision Service
                # Return Bad Request
                self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                self.send_error(400)
                return
            dmnRules = decisionServices[name]

            if len(bits) == 2:
                part = bits[1]
                self.data.logger.debug('GET - part {}'.format(part))
                sheets = dmnRules.getSheets()
                if part not in sheets:
                    self.data.logger.warning('GET: {} not in sheets'.format(part))
                    self.send_error(400)
                    return
                glossary = dmnRules.getTableGlossary(part)
                filename = secure_filename(name + '_' + part)
            else:
                part = None
                glossary = dmnRules.getGlossary()
                filename = secure_filename(name)

            self.data.logger.info('GET - type(dmnRules) {}'.format(type(dmnRules)))
            self.data.logger.info('GET - glossary {}'.format(glossary))
            
            openapi = self.mkOpenAPI(glossary, name, part)

            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Disposition', 'attachement; filename="{}.yaml"'.format(filename))
            self.end_headers()
            self.wfile.write(openapi.encode('utf-8'))
            return
        elif request.path[0:8] == '/delete/':         # Delete this Decision Service
            self.data.logger.info('GET {}'.format(self.path))
            name = unquote(request.path[8:])
            self.data.logger.info('GET - name {}'.format(name))
            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            if name not in decisionServices:            # Delete a Decision Service
                # Return Bad Request
                self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                self.send_error(400)
                return
                
            del decisionServices[name]

            # Assembling and send the HTML content
            self.message = '<html><head><title>Decision Central - delete</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            self.message += '<h3 style="text-align:center">Decision Service {} has been deleted</h3>'.format(name)
            self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))
        elif request.path[0:17] == '/download_delete/':         # Download the Open API specification
            self.data.logger.info('GET {}'.format(self.path))
            name = unquote(request.path[17:])
            self.data.logger.info('GET - name {}'.format(name))
            if name not in decisionServices:                # Check that we have this Decision Service
                # Return Bad Request
                self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                self.send_error(400)
                return

            openapi = self.mkDeleteOpenAPI(name)
            filename = secure_filename(name + '_delete')

            # Output the web page
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Disposition', 'attachement; filename="{}.yaml"'.format(filename))
            self.end_headers()
            self.wfile.write(openapi.encode('utf-8'))
            return
        else:
            self.data.logger.warning('GET: bad path - {}'.format(self.path))
            self.send_error(400)
            return


    def do_POST(self) :                # We only handle POST requests

        # Supported URLs are
        # /upload - upload a DMN compliant Excel workbook
        # /api/decisionServiceName - this decision Service

        # Reset all the globals
        self.data = DecisionCentralData('[desisionCentral-' + threading.current_thread().name + ']')

        self.data.logger.info('POST {}'.format(self.headers))

        # Set up logging for this new thread
        self.data.logStream = io.StringIO()        # Re-initialize logStream
        self.data.websh = logging.StreamHandler(self.data.logStream)
        self.data.websh.setFormatter(self.data.formatter)
        thisLevel = logging.WARNING

        if loggingLevel    :    # Change the logging level from "WARN" if the -v vebose option is specified
            thisLevel = logging_levels[loggingLevel]
        self.data.websh.setLevel(thisLevel)
        self.data.logger.addHandler(self.data.websh)

        # Parse the URl
        request = urlparse(self.path)
        # Check the URL
        if request.path == '/upload':
            # Parse the header for the content_type and boundary
            content_len = int(self.headers['Content-Length'])
            content_type = self.headers['Content-Type'].split(';')[0]
            boundary = self.headers['Content-Type'].split(';')[1].split('=')[1].strip()
            self.data.logger.info('GET {} {}'.format(content_type, boundary))
            if content_type != 'multipart/form-data':       # Only mulitpart/form-data is acceptable
                # Return Bad Request
                self.data.logger.warning('POST bad Content-Type')
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                self.send_error(400)
                del self.data
                return
            remainingbytes = content_len
            line = self.rfile.readline()            # Uploaded file should start with a boundary
            remainingbytes -= len(line)
            self.data.logger.info('POST - boundary {}'.format(boundary))
            self.data.logger.info('POST - line0 {}'.format(line))
            if not boundary in str(line):
                # Return Bad Request
                self.data.logger.warning('POST missing boundary')
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                self.send_error(400)
                del self.data
                return
            line = self.rfile.readline()            # Should be Content-Disposition, name and filename
            remainingbytes -= len(line)
            self.data.logger.info('POST - line1 {}'.format(line))
            if not 'Content-Disposition' in str(line):
                # Return Bad Request
                self.data.logger.warning('POST missing Content')
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                    self.send_error(400)
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                self.send_error(400)
                del self.data
                return
            # Get the filename
            contents = line.split(b';')
            filename = None
            for i in range(len(contents)):
                if 'filename' in str(contents[i]):
                        filename = str(contents[i]).split('=')[1]
                        if filename[0] == '"':
                            filename = filename[1:]
                        nextQuote = filename.find('"')
                        if nextQuote != -1:
                            filename = filename[:nextQuote]
            if filename is None:
                # Return the error
                self.data.logger.warning('POST missing filename')
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()

                # Assembling and send the HTML content
                self.message = '<html><head><title>Decision Central - No filename {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                self.message += '<h2 style="text-align:center">No filename found in  the upload request</h2>'.format(name)
                for i in range(len(status['errors'])):
                    self.message += '<pre>{}</pre>'.format(status['errors'][i])
                self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                self.message += '</body></html>'
                self.wfile.write(self.message.encode('utf-8'))
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                del self.data
                return
            filename = os.path.basename(filename)
            (filename, extn) = os.path.splitext(filename)
            if extn[1:].lower() not in ALLOWED_EXTENSIONS:
                # Return the error
                self.data.logger.warning('POST bad file extension:%s', extn)
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()

                # Assembling and send the HTML content
                self.message = '<html><head><title>Decision Central - Invalid filename extension {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                self.message += '<h2 style="text-align:center">Invalid file extension in the upload request</h2>'.format(name)
                for i in range(len(status['errors'])):
                    self.message += '<pre>{}</pre>'.format(status['errors'][i])
                self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                self.message += '</body></html>'
                self.wfile.write(self.message.encode('utf-8'))
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                del self.data
                return
            self.data.logger.info('POST - filename {}'.format(filename))
            line = self.rfile.readline()            # Should be Content-Type - skip
            remainingbytes -= len(line)
            self.data.logger.info('POST - line2 {}'.format(line))
            line = self.rfile.readline()            # Should be a blank line - skip
            remainingbytes -= len(line)
            self.data.logger.info('POST - line3 {}'.format(line))

            # Now read in the DMN compliant file
            line = self.rfile.readline()
            remainingbytes -= len(line)
            if line.strip() != '':                  # curl can send an extra blank line
                preline = line                      # The next line (or end of file) will tell us what this is
            else:
                preline = self.rfile.readline()     # The next line (or end of file) will tell us what this is
                remainingbytes -= len(preline)
            DMNfile = io.BytesIO()                 # Somewhere to store the DMN compliant file
            while remainingbytes > 0:               # Keep reading until the end
                line = self.rfile.readline()        # This line will define what we need to do with the previous line
                remainingbytes -= len(line)
                if boundary in str(line):           # This line is a boundary - trim and save the previous line
                    preline = preline[0:-1]
                    if preline.endswith(b'\r'):
                        preline = preline[0:-1]
                    DMNfile.write(preline)
                    break
                else:                               # Save the previous line (it does not need trimming)
                    DMNfile.write(preline)
                    preline = line

            dmnRules = pyDMNrules.DMN()             # An empty Rules Engine
            if extn[1:].lower() in Excel_EXTENSIONS:
                # Create a Decision Service from the uploaded file
                try:                # Convert file to workbook
                    wb = load_workbook(filename=DMNfile)
                except Exception as e:
                    # Return Bad Request
                    self.data.logger.warning('POST bad workbook')
                    self.send_error(400)
                    # Shutdown logging
                    for hdlr in self.data.logger.handlers:
                        hdlr.flush()
                    self.data.websh.flush()
                    self.data.logStream.close()
                    self.data.websh.close()
                    self.data.logger.removeHandler(self.data.websh)
                    del self.data
                    return

                status = dmnRules.use(wb)               # Add the rules from this DMN compliant Excel workbook
            else:
                DMNfile.seek(0)
                xml = DMNfile.read()
                status = dmnRules.useXML(xml)

            if 'errors' in status:
                # Return the error
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()

                # Assembling and send the HTML content
                self.message = '<html><head><title>Decision Central - Invalid DMN</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
                self.message += '<h2 style="text-align:center">There were errors in your DMN rules</h2>'
                for i in range(len(status['errors'])):
                    self.message += '<pre>{}</pre>'.format(status['errors'][i])
                self.message += '<pre>{}</pre>'.format(xml)
                self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                self.message += '</body></html>'
                self.wfile.write(self.message.encode('utf-8'))
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                del self.data
                return

            # Add this decision service to the list
            decisionServices[filename] = copy.deepcopy(dmnRules)

            # Output the web page
            self.send_response(201)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Assembling and send the HTML content
            self.message = '<html><head><title>Decision Central - uploaded</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'
            self.message += '<h2 style="text-align:center">Your DMN compatible Excel workbook or DMN compliant XML file has been successfully uploaded</h2>'
            self.message += '<h3 style="text-align:center">Your Decision Service has been created</h3>'
            self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
            self.message += '</body></html>'
            self.wfile.write(self.message.encode('utf-8'))

        elif request.path[0:5] == '/api/':         # An API request for a decision
            parts = unquote(request.path[5:])
            bits = parts.split('/')
            if len(bits) > 2:
                # Return Bad Request
                self.data.logger.warning('GET: {} is not a valid decisionService[/decisionTable]'.format(parts))
                self.send_error(400)
                return
            name = bits[0]
            if len(bits) == 2:
                part = bits[1]
                self.data.logger.debug('GET - part {}'.format(part))
                if not name.endswith('_table'):
                    self.data.logger.warning('GET: {} is not a valid decisionService[/decisionTable]'.format(parts))
                    self.send_error(400)
                    return
                else:
                    name = name[:-6]
                    if name not in decisionServices:                # Check that we have this Decision Service
                        # Return Bad Request
                        self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                        self.send_error(400)
                        return
                dmnRules = decisionServices[name]
                sheets = dmnRules.getSheets()
                if part not in sheets:
                    self.data.logger.warning('GET: {} not in sheets'.format(part))
                    self.send_error(400)
                    return
            else:
                part = None
                if name not in decisionServices:                # Check that we have this Decision Service
                    # Return Bad Request
                    self.data.logger.warning('GET: {} not in decisionServices'.format(name))
                    self.send_error(400)
                    return
                dmnRules = decisionServices[name]

            # Get the get the Variables and their values - could be from the web page, or a client app following the OpenAPI specification
            content_len = int(self.headers['Content-Length'])
            content_type = self.headers['Content-Type'].casefold()
            try:
                accept_type = self.headers['Accept'].casefold()
            except:
                accept_type = 'text/html'
            body = self.rfile.read(content_len)	# Get the URL encoded body
            self.data.data = {}
            if content_type == 'application/x-www-form-urlencoded':         # From the web page
                try:
                    params = parse_qs(body)
                    for variable in params:
                        thisVariable = variable.decode('ASCII').strip()
                        thisValue = params[variable][0].decode('ASCII').strip()
                        self.data.logger.info('POST {} {} {} {}'.format(thisVariable, thisValue, type(thisVariable), type(thisValue)))
                        self.data.data[thisVariable] = self.convertIn(thisValue)
                except:
                    # Return Bad Request
                    # Shutdown logging
                    self.data.logger.warning('POST - bad params')
                    for hdlr in self.data.logger.handlers:
                        hdlr.flush()
                    self.data.websh.flush()
                    self.data.logStream.close()
                    self.data.websh.close()
                    self.data.logger.removeHandler(self.data.websh)
                    del self.data
                    self.send_error(400)
                    return
            else:
                try:
                    self.data.data = json.loads(body)	# JSON payload
                except:
                    self.data.logger.critical('Bad JSON')
                    # Return Bad Request
                    # Shutdown logging
                    for hdlr in self.data.logger.handlers:
                        hdlr.flush()
                    del self.data
                    self.send_error(400)
                    return
                for thisVariable in self.data.data:
                    thisValue = self.data.data[thisVariable]
                    self.data.logger.info('POST {} {} {} {}'.format(thisVariable, thisValue, type(thisVariable), type(thisValue)))
                    self.data.data[thisVariable] = self.convertIn(thisValue)

            # Now make the decision
            self.data.logger.info('POST - making decision based upon {}'.format(self.data.data))
            if part is None:
                (status, self.data.newData) = dmnRules.decide(self.data.data)
            else:
                (status, self.data.newData) = dmnRules.decideTables(self.data.data, [part])
            if 'errors' in status:
                self.data.logger.warning('POST - bad status from decide()')
                self.data.logger.warning(status)

                if accept_type == 'application/json':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    newData = {}
                    newData['Result'] = {}
                    newData['Executed Rule'] = []
                    newData['Status'] = status
                    self.data.response = json.dumps(newData)
                    self.wfile.write(self.data.response.encode('utf-8'))
                else:
                    # Return the error
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()

                    # Assembling and send the HTML content
                    self.message = '<html><head><title>Decision Central - bad status from Decision Service {}</title><link rel="icon" href="data:,"></head><body style="font-size:120%">'.format(name)
                    self.message += '<h2 style="text-align:center">Your Decision Service {} returned a bad status</h2>'.format(name)
                    for i in range(len(status['errors'])):
                        self.message += '<pre>{}</pre>'.format(status['errors'][i])
                    self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                    self.message += '</body></html>'
                    self.wfile.write(self.message.encode('utf-8'))
                # Shutdown logging
                for hdlr in self.data.logger.handlers:
                    hdlr.flush()
                self.data.websh.flush()
                self.data.logStream.close()
                self.data.websh.close()
                self.data.logger.removeHandler(self.data.websh)
                del self.data
                return
            self.data.logger.info('POST - it worked {}'.format(self.data.newData))

            # Check if JSON or HTML response required
            if accept_type == 'application/json':
                # Return the results dictionary
                # The structure of the returned data varies depending upon the Hit Policy of the last executed Decision Table
                # We don't have the Hit Policy, but we can work it out
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()

                # Return the results dictionary
                returnData = {}
                returnData['Executed Rule'] = []
                if isinstance(self.data.newData, list):
                    for i in range(len(self.data.newData)):
                        if isinstance(self.data.newData[i]['Executed Rule'], list):           # The last executed Decision Table was RULE ORDER, OUTPUT ORDER or COLLECTION
                            for j in range(len(self.data.newData[i]['Executed Rule'])):
                                returnData['Executed Rule'].append([])
                                (executedDecision, decisionTable, ruleId) = self.data.newData[i]['Executed Rule'][j]
                                returnData['Executed Rule'][-1].append(executedDecision)
                                returnData['Executed Rule'][-1].append(decisionTable)
                                returnData['Executed Rule'][-1].append(ruleId)
                        else:
                            returnData['Executed Rule'].append([])
                            (executedDecision, decisionTable, ruleId) = self.data.newData[i]['Executed Rule']
                            returnData['Executed Rule'][-1].append(executedDecision)
                            returnData['Executed Rule'][-1].append(decisionTable)
                            returnData['Executed Rule'][-1].append(ruleId)
                    if len(self.data.newData) > 0:
                        self.data.newData = self.data.newData[-1]
                else:
                    if isinstance(self.data.newData['Executed Rule'], list):           # The last executed Decision Table was RULE ORDER, OUTPUT ORDER or COLLECTION
                        for i in range(len(self.data.newData['Executed Rule'])):
                            returnData['Executed Rule'].append([])
                            (executedDecision, decisionTable, ruleId) = self.data.newData['Executed Rule'][i]
                            returnData['Executed Rule'][-1].append(executedDecision)
                            returnData['Executed Rule'][-1].append(decisionTable)
                            returnData['Executed Rule'][-1].append(ruleId)
                    else:
                        (executedDecision, decisionTable, ruleId) = self.data.newData['Executed Rule']
                        returnData['Executed Rule'].append(executedDecision)
                        returnData['Executed Rule'].append(decisionTable)
                        returnData['Executed Rule'].append(ruleId)
                returnData['Result'] = {}
                if 'Result' in self.data.newData:
                    for variable in self.data.newData['Result']:
                        value = self.data.newData['Result'][variable]
                        returnData['Result'][variable] = self.convertOut(value)
                returnData['Status'] = status

                self.data.response = json.dumps(returnData)
                self.wfile.write(self.data.response.encode('utf-8'))
            else:
                # Now output the web page
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                # Assembling the HTML content
                self.message = '<html><head><title>The decision from Decision Service {}</title><link rel="icon" href="data:,"></head><body>'.format(name)
                self.message += '<h1>Decision Service {}</h1>'.format(name)
                self.message += '<h2>The Decision</h2>'
                self.message += '<table style="width:70%">'
                self.message += '<tr><th style="border:2px solid">Variable</th>'
                self.message += '<th style="border:2px solid">Value</th></tr>'
                if isinstance(self.data.newData, list) and (len(self.data.newData) > 0):
                    newData = self.data.newData[-1]
                else:
                    newData = self.data.newData
                for variable in newData['Result']:
                    if newData['Result'][variable] == '':
                        continue
                    self.message += '<tr><td style="border:2px solid">{}</td>'.format(variable)
                    self.message += '<td style="border:2px solid">{}</td></tr>'.format(str(newData['Result'][variable]))
                self.message += '</table>'
                self.message += '<h2>The Deciders</h2>'
                self.message += '<table style="width:70%">'
                self.message += '<tr><th style="border:2px solid">Executed Decision</th>'
                self.message += '<th style="border:2px solid">Decision Table</th>'
                self.message += '<th style="border:2px solid">Rule Id</th></tr>'
                if isinstance(newData['Executed Rule'], list):           # The last executed Decision Table was RULE ORDER, OUTPUT ORDER or COLLECTION
                    for j in range(len(newData['Executed Rule'])):
                        (executedDecision, decisionTable,ruleId) = newData['Executed Rule'][j]
                        self.message += '<tr><td style="border:2px solid">{}</td>'.format(executedDecision)
                        self.message += '<td style="border:2px solid">{}</td>'.format(decisionTable)
                        self.message += '<td style="border:2px solid">{}</td></tr>'.format(ruleId)
                        self.message += '<tr>'
                else:
                    (executedDecision, decisionTable,ruleId) = newData['Executed Rule']
                    self.message += '<tr><td style="border:2px solid">{}</td>'.format(executedDecision)
                    self.message += '<td style="border:2px solid">{}</td>'.format(decisionTable)
                    self.message += '<td style="border:2px solid">{}</td></tr>'.format(ruleId)
                    self.message += '<tr>'
                self.message += '</table>'
                self.message += '<p style="text-align:center"><b><a href="/show/{}">{} {}</a></b></p>'.format(name, 'Return to Decision Service', name)
                self.message += '<p style="text-align:center"><b><a href="/">{}</a></b></p>'.format('Return to Decision Central')
                self.message += '</body></html>'
                self.wfile.write(self.message.encode('utf-8'))
        else:
            self.data.logger.warning('POST - bad URL - %s', request.path)
            # Return Bad Request
            # Shutdown logging
            for hdlr in self.data.logger.handlers:
                hdlr.flush()
            self.data.websh.flush()
            self.data.logStream.close()
            self.data.websh.close()
            self.data.logger.removeHandler(self.data.websh)
            del self.data
            self.send_error(400)
            return

        # Shutdown logging
        for hdlr in self.data.logger.handlers:
            hdlr.flush()
        self.data.websh.flush()
        self.data.logStream.close()
        self.data.websh.close()
        self.data.logger.removeHandler(self.data.websh)
        del self.data
        return


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    '''
Handle requests in a separate thread.
    '''
    pass



# The main code
if __name__ == '__main__':
    '''
The main code
Parse the command line arguments and set up general error logging.
    '''

    # Get the script name (without the '.py' extension)
    progName = os.path.basename(sys.argv[0])
    progName = progName[0:-3]        # Strip off the .py ending

    # Define the command line options
    parser = argparse.ArgumentParser(prog=progName)
    parser.add_argument ('-p', '--port', dest='port', type=int, default=7777, help='The name of a logging directory')
    parser.add_argument ('-v', '--verbose', dest='verbose', type=int, choices=range(0,5),
                         help='The level of logging\n\t0=CRITICAL,1=ERROR,2=WARNING,3=INFO,4=DEBUG')
    parser.add_argument ('-L', '--logDir', dest='logDir', default='.', help='The name of a logging directory')
    parser.add_argument ('-l', '--logFile', metavar='logFile', dest='logFile', help='The name of the logging file')
    parser.add_argument ('args', nargs=argparse.REMAINDER)

    # Parse the command line options
    args = parser.parse_args()
    port = args.port
    loggingLevel = args.verbose
    logDir = args.logDir
    logFile = args.logFile

    # Configure the root logger which we use for start up and autocoding sys.stdin
    logging_levels = {0:logging.CRITICAL, 1:logging.ERROR, 2:logging.WARNING, 3:logging.INFO, 4:logging.DEBUG}
    logfmt = progName + ' %(threadName)s [%(asctime)s]: %(message)s'
    if loggingLevel and (loggingLevel not in logging_levels) :
        sys.stderr.write('Error - invalid logging verbosity (%d)\n' % (loggingLevel))
        parser.print_usage(sys.stderr)
        sys.stderr.flush()
        sys.exit(EX_USAGE)
    if logFile :        # If sending to a file then check if the log directory exists
        # Check that the logDir exists
        if not os.path.isdir(logDir) :
            sys.stderr.write('Error - logDir (%s) does not exits\n' % (logDir))
            parser.print_usage(sys.stderr)
            sys.stderr.flush()
            sys.exit(EX_USAGE)
        if loggingLevel :
            logging.basicConfig(format=logfmt, datefmt='%d/%m/%y %H:%M:%S %p', level=logging_levels[loggingLevel],
                                filemode='w', filename=os.path.join(logDir, logFile))
        else :
            logging.basicConfig(format=logfmt, datefmt='%d/%m/%y %H:%M:%S %p',
                                filemode='w', filename=os.path.join(logDir, logFile))
        print('Now logging to %s' % (os.path.join(logDir, logFile)))
        sys.stdout.flush()
    else :
        if loggingLevel :
            logging.basicConfig(format=logfmt, datefmt='%d/%m/%y %H:%M:%S %p', level=logging_levels[loggingLevel])
        else :
            logging.basicConfig(format=logfmt, datefmt='%d/%m/%y %H:%M:%S %p')
        print('Now logging to sys.stderr')
        sys.stdout.flush()

    # Create the child logger to which we will add the appropriate handler
    # But don't let it propogate to the root logger as we only want to use one or the other
    logger = logging.getLogger('DecisionCentral')
    logger.propagate = False


    # Set up the Decision Central Data
    this = DecisionCentralData(progName)
    this.logger = logging.getLogger()    # Use the root logger during start up

    print('Starting DecisionCental Service', file=sys.stdout)
    logger.propagate = True
    sys.stdout.flush()
    httpd = ThreadedHTTPServer(('', port), decisionCentralHandler)
    try:
        print('Started httpserver on port', port, file=sys.stdout)
        sys.stdout.flush()
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('Stopped httpserver on port', port, file=sys.stdout)
        sys.stdout.flush()

    httpd.server_close()
    try:
        ping = client.HTTPConnection('localhost', port)
        ping.request('GET', '/')
        response = ping.getresponse()
        ping.close()
        ping = client.HTTPConnection('localhost', port)
        ping.request('GET', '/')
        response = ping.getresponse()
        ping.close()
    except:
        pass
    for hdlr in this.logger.handlers:
        hdlr.flush()

    # Wrap it up
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
