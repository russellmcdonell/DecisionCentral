#!/usr/bin/env python

'''
A script to a DMN decision service being hosted by DecisionCentral.

SYNOPSIS
$ python questioner.py [-v loggingLevel|--verbose=logingLevel] [-L logDir|--logDir=logDir] [-l logfile|--logfile=logfile]
                       [-u url|--url=url] [-i inputCSV|--inputCSV=inputCSV] [-o outputCSV|--outputCSV=outputCSV]

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
(default = 'http://localhost:7777/api/Example1')

-i inputCSV|--inputCSV=inputCSV
The input CSV file of questions (data).
It must have headings, which will be the names of Variables associated with the decision service.
(default = 'questions.csv')

-o outputCSV|--outputCSV=outputCSV
The outputCSV file of answers (decisions).
(default = 'answers.csv')


The questioner sends JSON data to a decision service hosted on a DecisionCentral server.
The decision service is defined by a url (default=http://localhost:7777/api/Example1)
The data (questions) is read from a CSV file (default=questions.csv)
The answers (decisions) are writen to a CSV file (default=answers.csv)

'''

# Import all the modules that make life easy
import sys
import os
import io
import argparse
import logging
import csv
import json
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
    parser.add_argument ('-u', '--url', dest='url', default="http://localhost:7777/api/Example1", help='The URL of a decision service hosted by DecisionCentral')
    parser.add_argument ('-i', '--inputCSV', dest='inputCSV', default="questions.csv", help='The name of the inputCSV file')
    parser.add_argument ('-o', '--outputCSV', dest='outputCSV', default="answers.csv", help='The name of the outputCSV file')
    parser.add_argument ('-v', '--verbose', dest='verbose', type=int, choices=range(0,5),
                         help='The level of logging\n\t0=CRITICAL,1=ERROR,2=WARNING,3=INFO,4=DEBUG')
    parser.add_argument ('-L', '--logDir', dest='logDir', default='.', help='The name of a logging directory')
    parser.add_argument ('-l', '--logFile', metavar='logFile', dest='logFile', help='The name of the logging file')
    parser.add_argument ('args', nargs=argparse.REMAINDER)

    # Parse the command line options
    args = parser.parse_args()
    url = args.url
    inputCSV = args.inputCSV
    outputCSV = args.outputCSV
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
        sys.exit(NO_HOST)
    decisionServiceHost = urlBits.hostname
    if urlBits.port is None:
        decisionServicePort = 80
    else:
        decisionServicePort = urlBits.port

    decisionServiceHeaders = {'Content-type':'application/json', 'Accept':'application/json'}
    try :
        decisionServiceConnection = client.HTTPConnection(decisionServiceHost, decisionServicePort)
        decisionServiceConnection.close()
    except (client.NotConnected, client.InvalidURL, client.UnknownProtocol,client.UnknownTransferEncoding,client.UnimplementedFileMode,   client.IncompleteRead, client.ImproperConnectionState, client.CannotSendRequest, client.CannotSendHeader, client.ResponseNotReady, client.BadStatusLine) as e:
        logging.critical('Cannot connect to the decisionService Service on host (%s) and port (%s). Error:%s', decisionServiceHost, decisionServicePort, str(e))
        logging.shutdown()
        sys.stdout.flush()
        sys.exit(EX_UNAVAILABLE)
    logging.info('Tested connected to %s:%d', decisionServiceHost, decisionServicePort)

    # Create the answers file
    with open(outputCSV, 'wt', newline='') as outputFile:
        csvwriter = csv.writer(outputFile, dialect=csv.excel)
        needHeader = True
        
        # Open the questions file
        with open(inputCSV, 'rt', newline='') as inputFile:
            csvreader = csv.DictReader(inputFile, dialect=csv.excel)
            for row in csvreader:
                # Map a few booleans
                for key in row:
                    if row[key] == 'True':
                        row[key] = True
                    elif row[key] == 'true':
                        row[key] = True
                    elif row[key] == 'TRUE':
                        row[key] = True
                    elif row[key] == 'False':
                        row[key] = False
                    elif row[key] == 'false':
                        row[key] = False
                    elif row[key] == 'FALSE':
                        row[key] = False
                    elif row[key] == 'None':
                        row[key] = None
                    elif row[key] == 'null':
                        row[key] = None
                    elif row[key] == '':
                        row[key] = None
                
                # Get the results from the decision service
                logging.info('Questioning: %s', str(row))
                params = json.dumps(row)
                try :
                    decisionServiceConnection = client.HTTPConnection(decisionServiceHost, decisionServicePort)
                    decisionServiceConnection.request('POST', url, params, decisionServiceHeaders)
                    response = decisionServiceConnection.getresponse()
                    if response.status != 200 :
                        logging.critical('Invalid response from Decision Service:error %s', str(response.status))
                        logging.shutdown()
                        sys.stdout.flush()
                        sys.exit(EX_PROTOCOL)
                    responseData = response.read()
                    decisionServiceConnection.close()
                except (client.NotConnected, client.InvalidURL, client.UnknownProtocol,client.UnknownTransferEncoding,client.UnimplementedFileMode,   client.IncompleteRead, client.ImproperConnectionState, client.CannotSendRequest, client.CannotSendHeader, client.ResponseNotReady, client.BadStatusLine) as e:
                    logging.critical('Decision Service error:%s', str(e))
                    logging.shutdown()
                    sys.stdout.flush()
                    sys.exit(EX_PROTOCOL)

                try :
                    answer = json.loads(responseData)
                except ValueError as e :
                    logging.critical('Invalid data from Decision Service:error %s', e)
                    logging.shutdown()
                    sys.stdout.flush()
                    sys.exit(EX_PROTOCOL)

                logging.info('Decision Service success')
                logging.info('Decision Service returned:%s', str(answer))
                if needHeader:
                    header = []
                    for key in answer:
                        if key == 'Result':
                            for resultKey in answer[key]:
                                header.append(resultKey)
                    header.append('Excuted Decision')
                    header.append('Decision Table')
                    header.append('Rule Id')
                    csvwriter.writerow(header)
                    needHeader = False

                # Save the answer
                output = []
                for key in answer['Result']:
                    output.append(answer['Result'][key])
                output.append(answer['Executed Rule'][0])
                output.append(answer['Executed Rule'][1])
                output.append(answer['Executed Rule'][2])
                csvwriter.writerow(output)
                logging.info('Answer saved')
