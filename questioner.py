#!/usr/bin/env python

'''
A script to call a DMN decision service being hosted by DecisionCentral.

SYNOPSIS
$ python questioner.py [-v loggingLevel|--verbose=logingLevel] [-L logDir|--logDir=logDir] [-l logfile|--logfile=logfile]
                       [-u url|--url=url] [-i inputfile|--inputfile=inputfile] [-o outputfile|--outputfile=outputfile]

REQUIRED


OPTIONS
-v loggingLevel|--verbose=loggingLevel
Set the level of logging that you want (defaut INFO).

-L logDir
The directory where the log file will be written.

-l logfile|--logfile=logfile
The name of a logging file where you want all messages captured.

-u url|--url=url
The url of the decision service hosted by DecisionCentral
(default = 'http://localhost:5000/api/Example1')

-i inputfile|--inputfile=inputfile
The input Excel file of questions (data).
It must have headings, which will be the names of Variables associated with the decision service.
(default = 'questions.xlsx')

-o outputfile|--outputfile=outputfile
The output Excel file of answers (decisions).
(default = 'answers.xlsx')


The questioner sends JSON data to a decision service hosted on a DecisionCentral server.
The decision service is defined by a url (default=http://localhost:5000/api/Example1)
The data (questions) is read from an Excel file (default=questions.xlsx)
The answers (decisions) are writen to an Excel file (default=answers.xlsx)

'''

# Import all the modules that make life easy
import sys
import os
import io
import argparse
import logging
from openpyxl import Workbook
import pandas as pd
import pySFeel
import requests
import json
import datetime
from urllib.parse import urlparse, urlencode, parse_qs, quote, unquote
from http.client import parse_headers
from http import client

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
        return thisValue
    elif thisValue is None:
        return thisValue
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
    parser.add_argument ('-u', '--url', dest='url', default="http://localhost:5000/api/Example1", help='The URL of a decision service hosted by DecisionCentral (default=http://localhost:5000/api/Example1)')
    parser.add_argument ('-i', '--inputfile', dest='inputfile', default="questions.xlsx", help='The name of the inputfile file (default=questions.xlsx)')
    parser.add_argument ('-o', '--outputfile', dest='outputfile', default="answers.xlsx", help='The name of the outputfile file (default=answers.xlsx)')
    parser.add_argument ('-v', '--verbose', dest='verbose', type=int, choices=range(0,5),
                         help='The level of logging\n\t0=CRITICAL,1=ERROR,2=WARNING,3=INFO,4=DEBUG')
    parser.add_argument ('-L', '--logDir', dest='logDir', default='.', help='The name of a logging directory')
    parser.add_argument ('-l', '--logFile', metavar='logFile', dest='logFile', help='The name of the logging file')

    # Parse the command line options
    args = parser.parse_args()
    url = args.url
    inputfile = args.inputfile
    outputfile = args.outputfile
    loggingLevel = args.verbose
    logDir = args.logDir
    logFile = args.logFile

    # Configure logging
    logging_levels = {0:logging.CRITICAL, 1:logging.ERROR, 2:logging.WARNING, 3:logging.INFO, 4:logging.DEBUG}
    logfmt = '%(filename)s [%(asctime)s]: %(message)s'
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
    logging.info('Logging started')

    # Make sure we have connectivity to the decision service
    urlBits = urlparse(url, allow_fragments=False)
    if urlBits.hostname is None:
        logging.critical('No hostname in URL - try full URL - e.g. http://host:port/api/decisionService')
        logging.shutdown()
        sys.stdout.flush()
        sys.exit(EX_NOHOST)
    decisionServiceHost = urlBits.hostname
    logging.info('host:%s', decisionServiceHost)
    if urlBits.port is None:
        if urlBits.scheme == 'https':
            logging.info('https - using port 443')
            decisionServicePort = 443
        else:
            decisionServicePort = 80
    else:
        decisionServicePort = urlBits.port
    logging.info('port:%s', decisionServicePort)

    decisionServiceHeaders = {'Content-type':'application/json', 'Accept':'application/json'}
    logging.info('headers:%s', decisionServiceHeaders)
    try :
        if urlBits.scheme == 'https':
            logging.info('https - testing connection')
            decisionServiceConnection = client.HTTPSConnection(decisionServiceHost, decisionServicePort)
        else:
            decisionServiceConnection = client.HTTPConnection(decisionServiceHost, decisionServicePort)
        decisionServiceConnection.close()
    except (client.NotConnected, client.InvalidURL, client.UnknownProtocol,client.UnknownTransferEncoding,client.UnimplementedFileMode,   client.IncompleteRead, client.ImproperConnectionState, client.CannotSendRequest, client.CannotSendHeader, client.ResponseNotReady, client.BadStatusLine) as e:
        logging.critical('Cannot connect to the decisionService Service on host (%s) and port (%s). Error:%s', decisionServiceHost, decisionServicePort, str(e))
        logging.shutdown()
        sys.stdout.flush()
        sys.exit(EX_UNAVAILABLE)
    logging.info('Tested connected to %s:%d', decisionServiceHost, decisionServicePort)

    # Read in questions
    dfInput = pd.read_excel(inputfile)

    # Create a workbook for the answers
    wb = Workbook()
    ws = wb.active

    # Ask the questions and get the answer
    first = True
    heading = []
    for index, row in dfInput.iterrows():
        inrow = {}
        for key in row.keys():
            if first:
                heading.append(key)
            if pd.isna(row[key]):            # Map missing data to None
                inrow[key] = None
            else:
                inrow[key] = convertOut(row[key])
        request = requests.post(url, headers=decisionServiceHeaders, json=inrow)
        if request.status_code != requests.codes.ok:
            print('failed - bad request - ', request.text)
            logging.info('failed - bad request - %s', request.text)
            continue
        try:
            newData = request.json()
        except:
            print('failed - bad request - ', request.text)
            logging.info('failed - bad request - %s', request.text)
            continue
        status = newData['Status']
        result = newData['Result']
        executedRule = newData['Executed Rule']
        if 'errors' in status:
            print('failed - bad status - ', '/'.join(status['errors']))
            logging.info('failed - bad status - %s', '/'.join(status['errors']))
            continue

        if first:
            for key in result.keys():
                if key not in heading:
                    heading.append(key)
            ws.append(heading)
            first = False

        # Create the output row
        outrow = []
        for i in range(len(heading)):
            outrow.append(convertOut(result[heading[i]]))
        ws.append(outrow)

    # Create the answers file
    wb.save(outputfile)

