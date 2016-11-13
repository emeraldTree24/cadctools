#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# ***********************************************************************
# ******************  CANADIAN ASTRONOMY DATA CENTRE  *******************
# *************  CENTRE CANADIEN DE DONNÉES ASTRONOMIQUES  **************
#
#  (c) 2016.                            (c) 2016.
#  Government of Canada                 Gouvernement du Canada
#  National Research Council            Conseil national de recherches
#  Ottawa, Canada, K1A 0R6              Ottawa, Canada, K1A 0R6
#  All rights reserved                  Tous droits réservés
#
#  NRC disclaims any warranties,        Le CNRC dénie toute garantie
#  expressed, implied, or               énoncée, implicite ou légale,
#  statutory, of any kind with          de quelque nature que ce
#  respect to the software,             soit, concernant le logiciel,
#  including without limitation         y compris sans restriction
#  any warranty of merchantability      toute garantie de valeur
#  or fitness for a particular          marchande ou de pertinence
#  purpose. NRC shall not be            pour un usage particulier.
#  liable in any event for any          Le CNRC ne pourra en aucun cas
#  damages, whether direct or           être tenu responsable de tout
#  indirect, special or general,        dommage, direct ou indirect,
#  consequential or incidental,         particulier ou général,
#  arising from the use of the          accessoire ou fortuit, résultant
#  software.  Neither the name          de l'utilisation du logiciel. Ni
#  of the National Research             le nom du Conseil National de
#  Council of Canada nor the            Recherches du Canada ni les noms
#  names of its contributors may        de ses  participants ne peuvent
#  be used to endorse or promote        être utilisés pour approuver ou
#  products derived from this           promouvoir les produits dérivés
#  software without specific prior      de ce logiciel sans autorisation
#  written permission.                  préalable et particulière
#                                       par écrit.
#
#  This file is part of the             Ce fichier fait partie du projet
#  OpenCADC project.                    OpenCADC.
#
#  OpenCADC is free software:           OpenCADC est un logiciel libre ;
#  you can redistribute it and/or       vous pouvez le redistribuer ou le
#  modify it under the terms of         modifier suivant les termes de
#  the GNU Affero General Public        la “GNU Affero General Public
#  License as published by the          License” telle que publiée
#  Free Software Foundation,            par la Free Software Foundation
#  either version 3 of the              : soit la version 3 de cette
#  License, or (at your option)         licence, soit (à votre gré)
#  any later version.                   toute version ultérieure.
#
#  OpenCADC is distributed in the       OpenCADC est distribué
#  hope that it will be useful,         dans l’espoir qu’il vous
#  but WITHOUT ANY WARRANTY;            sera utile, mais SANS AUCUNE
#  without even the implied             GARANTIE : sans même la garantie
#  warranty of MERCHANTABILITY          implicite de COMMERCIALISABILITÉ
#  or FITNESS FOR A PARTICULAR          ni d’ADÉQUATION À UN OBJECTIF
#  PURPOSE.  See the GNU Affero         PARTICULIER. Consultez la Licence
#  General Public License for           Générale Publique GNU Affero
#  more details.                        pour plus de détails.
#
#  You should have received             Vous devriez avoir reçu une
#  a copy of the GNU Affero             copie de la Licence Générale
#  General Public License along         Publique GNU Affero avec
#  with OpenCADC.  If not, see          OpenCADC ; si ce n’est
#  <http://www.gnu.org/licenses/>.      pas le cas, consultez :
#                                       <http://www.gnu.org/licenses/>.
#
#
# ***********************************************************************
import requests
import logging
import os
from cadctools import exceptions
import time
import auth

BUFSIZE = 8388608  # Size of read/write buffer
MAX_RETRY_DELAY = 128  # maximum delay between retries
DEFAULT_RETRY_DELAY = 30  # start delay between retries when Try_After not sent by server.
MAX_RETRY_TIME = 900  # maximum time for retries before giving up...
CONNECTION_TIMEOUT = 30  # seconds before HTTP connection should drop, should be less than DAEMON timeout in vofs

# try to disable the unverified HTTPS call warnings
try:
    requests.packages.urllib3.disable_warnings()
except:
    pass



class RetrySession(requests.Session):

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger('RetrySession')
        super(RetrySession, self).__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        """
        Send a given PreparedRequest, wrapping the connection to service in try/except that retries on
        Connection reset by peer.
        :param request: The prepared request to send._session
        :param kwargs: Any keywords the adaptor for the request accepts.
        :return: the response
        :rtype: requests.Response
        """

        total_delay = 0
        current_delay = DEFAULT_RETRY_DELAY
        self.logger.debug("--------------->>>> Sending request {0}  to server.".format(request))
        while total_delay < MAX_RETRY_DELAY:
            try:
                return super(RetrySession, self).send(request, **kwargs)
            except requests.exceptions.ConnectionError as ce:
                self.logger.debug("Caught exception: {0}".format(ce))
                if ce.errno != 104:
                    # Only continue trying on a reset by peer error.
                    raise ce
                time.sleep(current_delay)
                total_delay += current_delay
                current_delay = MAX_RETRY_DELAY > current_delay * 2 and current_delay * 2 or MAX_RETRY_DELAY
        raise


class BaseWsClient(object):
    """Web Service client primarily for CADC services"""

    def __init__(self, anon = True, cert_file = None,
                 service='www.canfar.phys.uvic.ca', agent = None):
        """
        Client constructor
        :param anon  -- anonymous access or not. If not anonymous and
        cert_file present, use it otherwise use basic authentication
        :param cert_file -- location of the X509 certificate file.
        :param service -- URI or URL of the service being accessed
        :param agent -- Name of the agent (application) that accesses the service
        """

        self.logger = logging.getLogger('BaseWsClient')
        self._session = None
        self.certificate_file_location = None
        self.basic_auth = None
        self.anon = None


        #TODO check if uri and resolve it
        self.host = service
        self.agent = agent
        # Unless the caller specifically requests an anonymous client,
        # check first for a certificate, then an externally created
        # HTTPBasicAuth object, and finally a name+password in .netrc.

        if not anon:
            if (cert_file is not None) and (cert_file is not ''):
                if os.path.isfile(cert_file):
                    self.certificate_file_location = cert_file
                else:
                    logging.warn( "Unable to open supplied certfile '%s':" % cert_file +\
                        " Ignoring.")
                    self.basic_auth = auth.get_user_password(service)
        else:
            self.anon = True


        self.logger.debug(
            "Client anonymous: %s, certfile: %s, name/password: %s" % \
                (str(self.anon), str(self.certificate_file_location),
                 str(self.basic_auth is not None)) ) #TODO hide password

        # Base URL for web services.
        # Clients will probably append a specific service
        if self.certificate_file_location:
            self.protocol = 'https'
        else:
            # For both anonymous and name/password authentication
            self.protocol = 'http'

        self.base_url = '%s://%s' % (self.protocol, self.host)

        # Clients should add entries to this dict for specialized
        # conversion of HTTP error codes into particular exceptions.
        #
        # Use this form to include a search string in the response to
        # handle multiple possibilities for a single HTTP code.
        #     XXX : {'SEARCHSTRING1' : exceptionInstance1,
        #            'SEARCHSTRING2' : exceptionInstance2}
        #
        # Otherwise provide a simple HTTP code -> exception mapping
        #     XXX : exceptionInstance
        #
        # The actual conversion is performed by get_exception()
        self._HTTP_STATUS_CODE_EXCEPTIONS = {
            401 : exceptions.UnauthorizedException()
            }


    def _post(self, *args, **kwargs):
        """Wrapper for POST so that we use this client's session"""
        return self._get_session().post(*args, **kwargs)

    def _put(self, *args, **kwargs):
        """Wrapper for PUT so that we use this client's session"""
        return self._get_session().put(*args, **kwargs)

    def _get(self, resource=None, params=None, **kwargs):
        """Wrapper for GET so that we use this client's session"""
        url = self.base_url
        if resource is not None:
            if str(resource).startswith('/'):
                url += str(resource)
            else:
                url += '/' + str(resource)

        return self._get_session().get(url, params=params, **kwargs)

    def _delete(self, *args, **kwargs):
        """Wrapper for DELETE so that we use this client's session"""
        return self._get_session().delete(*args, **kwargs)

    def _head(self, *args, **kwargs):
        """Wrapper for HEAD so that we use this client's session"""
        return self._get_session().head(*args, **kwargs)


    def _get_session(self):
        # Note that the cert goes into the adapter, but we can also
        # use name/password for the auth. We may want to enforce the
        # usage of only the cert in case both name/password and cert
        # are provided.
        if(self._session is None):
            self.logger.debug('Creating session.')
            self._session = RetrySession()
            print(str(self._session.cookies))
            if self.certificate_file_location is not None:
                self._session.cert = (self.certificate_file_location, self.certificate_file_location)
            else:
                if self.basic_auth is not None:
                    self._session.auth = self.basic_auth

        #self._session.headers.update({"User-Agent": self.agent})
        assert isinstance(self._session, requests.Session)
        print(str(requests.Session().cookies))
        return self._session
