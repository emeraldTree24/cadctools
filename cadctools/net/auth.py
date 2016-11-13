#!python

import getpass
import netrc
import argparse
import os
import signal
import sys
import requests

CERT_ENDPOINT = "/cred/proxyCert"
CERT_SERVER = "www.canfar.phys.uvic.ca"


def get_cert(cert_server=None,
             cert_endpoint=None, **kwargs):
    """Access the cadc certificate server.

    :param cert_server: the http server that will provide the certificate
    :ptype cert_server: str
    :param cert_endpoint: the endpoint on the server where the certificate service is
    :ptype cert_endpoint: str
    :param kwargs: not really any, but maybe daysValid.
    :ptype daysValid: int

    :return content of the certificate

    """

    cert_server = cert_server is None and CERT_SERVER or cert_server
    cert_endpoint = cert_endpoint is None and CERT_ENDPOINT or cert_endpoint

    username, passwd = get_user_password(cert_server)

    url = "http://{0}/{1}".format(cert_server, cert_endpoint)
    resp = requests.get(url, params=kwargs, auth=(username, passwd))
    resp.raise_for_status()
    return resp.content


def get_user_password(realm):
    """"Gett the username/password for realm from .netrc file or prompt the user

    :param realm: the server realm this user/password combination is for
    :ptype realm: str
    :return (username, password)
    """
    if os.access(os.path.join(os.environ.get('HOME', '/'), ".netrc"), os.R_OK):
        auth = netrc.netrc().authenticators(realm)
    else:
        auth = False
    if not auth:
        sys.stdout.write("{0} Username: ".format(realm))
        username = sys.stdin.readline().strip('\n')
        password = getpass.getpass().strip('\n')
    else:
        username = auth[0]
        password = auth[2]
    return username, password




def get_cert_main():
    """ Client to download an X509 certificate and save it in users home directory"""

    def _signal_handler(signal, frame):
        sys.stderr.write("\n")
        sys.exit(-1)

    signal.signal(signal.SIGINT, _signal_handler)

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description=("Retrieve a security certificate for interation with a Web service "
                                                  "such as VOSpace. Certificate will be valid for daysValid and stored "
                                                  "as local file cert_filename. First looks for an entry in the users "
                                                  ".netrc  matching the realm {0}, the user is prompted for a username "
                                                  "and password if no entry is found.".format(CERT_SERVER)))

    parser.add_argument('--daysValid', type=int, default=10, help='Number of days the cetificate should be valid.')
    parser.add_argument('--cert-filename',
                        default=os.path.join(os.getenv('HOME', '/tmp'), '.ssl/cadcproxy.pem'),
                        help="Filesysm location to store the proxy certifcate.")
    parser.add_argument('--cert-server',
                        default=CERT_SERVER,
                        help="Certificate server network address.")

    args = parser.parse_args()

    dirname = os.path.dirname(args.cert_filename)
    try:
        os.makedirs(dirname)
    except OSError as oex:
        if os.path.isdir(dirname):
            pass
        elif oex.errno == 20 or oex.errno == 17:
            sys.stderr.write("%s : %s \n" % (str(oex), dirname))
            sys.stderr.write("Expected %s to be a directory.\n" % dirname)
            sys.exit(oex.errno)
        else:
            raise oex


    retry = True
    while retry:
        try:
            #if args.cert_filename is None:
            #    cert_filename = os.path.join(os.getenv("HOME", "/tmp"), ".ssl/cadcproxy.pem")

            cert = get_cert(cert_server=args.cert_server,
                     daysValid=args.daysValid)
            with open(args.cert_filename, 'w') as w:
                w.write(cert)
            retry = False
        except OSError as ose:
            if ose.errno != 401:
                sys.stderr.write(str(ose))
                return getattr(ose, 'errno', 1)
            else:
                sys.stderr.write("Access denied\n")
        except Exception as ex:
            sys.stderr.write(str(ex))
            return getattr(ex, 'errno', 1)
