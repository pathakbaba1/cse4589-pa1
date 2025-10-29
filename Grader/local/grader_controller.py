#!/usr/bin/python
#
# This file is part of CSE 489/589 Grader.
#
# CSE 489/589 Grader is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# CSE 489/589 Grader is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with CSE 489/589 Grader. If not, see <http://www.gnu.org/licenses/>.
#

__author__ = "Swetank Kumar Saha (swetankk@buffalo.edu)"
__copyright__ = "Copyright (C) 2017 Swetank Kumar Saha"
__license__ = "GNU GPL"
__version__ = "1.3.2"

import argparse
import sys
import os
import subprocess
import time
import random
import traceback
import threading

import utils

parser = argparse.ArgumentParser(description='CSE 489/589 Grader Controller v'+__version__)

requiredArgs = parser.add_argument_group('required named arguments')
requiredArgs.add_argument('-c', '--config', dest='config', type=argparse.FileType('r'), nargs=1, help='configuration file', required=True)
requiredArgs.add_argument('-s', '--submission', dest='submission', type=str, nargs=1 , help='path to submission tarball', required=True)
requiredArgs.add_argument('-t', '--test', dest='test', type=str, nargs=1, help='test name', required=True)

optionalArgs = parser.add_argument_group('optional named arguments')
optionalArgs.add_argument('-nu', '--no-upload', dest='no_upload', action='store_true', help='suppress file upload')
optionalArgs.add_argument('-nb', '--no-build', dest='no_build', action='store_true', help='suppress submission build')

if __name__ == '__main__':
    args = parser.parse_args()

    cfg = utils.readConfiguration(args.config[0])

    utils.print_regular('Initializing grading servers ...')

    utils.GRADING_SERVER_PORT = random.randint(55000, 65000)
    launcher_port = cfg.getint('HTTPLauncher', 'port')
    tarball = args.submission[0]

    failed_servers = []
    healthy_servers = []

    for server in utils.GRADING_SERVERS_HOSTNAME:
        print
        print server
        server_ok = True
        
        try:
            # Upload submission
            if not args.no_upload:
                utils.print_regular('Uploading submission ...')
                try:
                    # Add --max-time for curl timeout instead of subprocess timeout (Python 2.7 compatible)
                    print subprocess.check_output(['curl', '--max-time', '30', 'http://'+server+':'+str(launcher_port), '-F', 'submit=@'+tarball], stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError as e:
                    print '\033[31mERROR: Upload failed - %s\033[0m' % str(e)
                    server_ok = False
                except Exception as e:
                    print '\033[31mERROR: Upload failed - %s\033[0m' % str(e)
                    server_ok = False

            # Build submission
            if server_ok and not args.no_build:
                utils.print_regular('Building submission ...')
                message = {'action': 'build', 'tarball': os.path.basename(tarball)}
                response = utils.doGET(server, str(launcher_port),  message)
                print response
                if response == 'FAILED': 
                    server_ok = False

            # Init. server
            if server_ok:
                utils.print_regular('Starting grading server ...')
                message = {'action': 'init',
                            'remote_grader_path': cfg.get('GradingServer', 'dir-grader'),
                            'python': cfg.get('GradingServer', 'path-python'),
                            'port': str(utils.GRADING_SERVER_PORT)}
                response = utils.doGET(server, launcher_port, message)
                print response
                if response == 'FAILED': 
                    server_ok = False
                    
        except Exception as e:
            print '\033[31mERROR: Server initialization failed - %s\033[0m' % str(e)
            server_ok = False
        
        if server_ok:
            healthy_servers.append(server)
            print '\033[32m✓ Server %s is ready\033[0m' % server
        else:
            failed_servers.append(server)
            print '\033[31m✗ Server %s failed - will be excluded from tests\033[0m' % server
    
    # Update the global server lists to only include healthy servers
    if len(healthy_servers) == 0:
        print '\033[31mFATAL: No healthy servers available. Cannot proceed with grading.\033[0m'
        sys.exit(1)
    
    # Rebuild the GRADING_SERVERS lists with only healthy servers
    utils.GRADING_SERVERS_HOSTNAME = []
    utils.GRADING_SERVERS_IP = []
    for server in healthy_servers:
        idx = utils.GRADING_SERVERS_ALL_HOSTNAME.index(server) if server in utils.GRADING_SERVERS_ALL_HOSTNAME else utils.GRADING_SERVERS_HOSTNAME.index(server)
        utils.GRADING_SERVERS_HOSTNAME.append(server)
        try:
            utils.GRADING_SERVERS_IP.append(utils.resolveIP(server))
        except:
            # If we can't resolve, try to use the original IP if available
            if idx < len(utils.GRADING_SERVERS_IP):
                utils.GRADING_SERVERS_IP.append(utils.GRADING_SERVERS_IP[idx])
    
    print
    print '\033[33m' + '='*60 + '\033[0m'
    print '\033[33mSERVER STATUS SUMMARY\033[0m'
    print '\033[33m' + '='*60 + '\033[0m'
    print 'Healthy Servers: %d' % len(healthy_servers)
    print 'Failed Servers: %d' % len(failed_servers)
    if failed_servers:
        print '\033[31mExcluded: %s\033[0m' % ', '.join(failed_servers)
    print '\033[33m' + '='*60 + '\033[0m'
    print

    try:
        # Wait for all servers to init.
        time.sleep(3)

        remote_grading_dir = utils.doGET(server, launcher_port, {'action': 'get-gdir'})
        binary = os.path.join(*[remote_grading_dir, os.path.splitext(os.path.basename(tarball))[0], cfg.get('Grader', 'binary')])
        test_name = args.test[0]

        import pa1_grader
        print
        utils.print_regular('Grading for: %s ...' % (test_name))
        getattr(pa1_grader, test_name)(binary)
    except:
        traceback.print_exc()
    finally:
        # Wait for any left-over threads to finish
        while(len(threading.enumerate()) > 1): continue

        # Kill remote servers
        for server in utils.GRADING_SERVERS_HOSTNAME:
            utils.doGET(server, launcher_port, {'action': 'terminate', 'port': str(utils.GRADING_SERVER_PORT)})
