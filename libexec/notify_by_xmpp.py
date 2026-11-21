#!/usr/bin/env python3
# skvidal@fedoraproject.org, modified by David Laval
# gplv2+
"""Send a Shinken notification as an XMPP (Jabber) message.

Usage (see etc/commands/notify-*-by-xmpp.cfg)::

    notify_by_xmpp.py -a notify_by_xmpp.ini "message" user@example.org [...]

The ini file holds the account used to send the message::

    [xmpp_account]
    server=xmpp.example.org
    port=5222
    username=shinken@example.org
    password=secret
    resource=monitoring

Without recipients, the message is sent to every contact of the roster.
Requires the ``xmpppy`` package (``pip install xmpppy``).
Exit codes: 0 sent, 2 delivery failed, 3 configuration or usage error.
"""

import argparse
import configparser
import os
import sys
import warnings

EXIT_OK = 0
EXIT_SEND_FAILED = 2
EXIT_USAGE = 3

DEFAULTS = {
    "server": "jabber.org",
    "port": "5222",
    "resource": "monitoring",
}


def error(message, code):
    print("ERROR: %s" % message, file=sys.stderr)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send a notification over XMPP.")
    parser.add_argument("-a", dest="authfile", required=True,
                        help="ini file with username/password/server/port/resource")
    parser.add_argument("message", help="Message text (literal \\n become new lines)")
    parser.add_argument("recipients", nargs="*", help="JIDs; default: whole roster")
    opts = parser.parse_args(argv)

    if not os.path.exists(opts.authfile):
        return error("config/auth file %s not found" % opts.authfile, EXIT_USAGE)
    conf = configparser.ConfigParser(defaults=DEFAULTS)
    conf.read(opts.authfile, encoding="utf-8")
    if not (conf.has_section("xmpp_account")
            and conf.has_option("xmpp_account", "username")
            and conf.has_option("xmpp_account", "password")):
        return error("section [xmpp_account] with username and password required in %s"
                     % opts.authfile, EXIT_USAGE)
    server = conf.get("xmpp_account", "server")
    username = conf.get("xmpp_account", "username")
    password = conf.get("xmpp_account", "password")
    resource = conf.get("xmpp_account", "resource")
    port = conf.getint("xmpp_account", "port")

    try:
        warnings.simplefilter("ignore")
        import xmpp
        from xmpp.protocol import Message
    except ImportError:
        return error("the xmpppy package is required (pip install xmpppy)", EXIT_USAGE)

    message = opts.message.replace("\\n", "\n")
    client = xmpp.Client(server=server, port=port, debug=[])
    if not client.connect():
        return error("could not connect to server %s:%s" % (server, port), EXIT_SEND_FAILED)
    if not client.auth(user=username, password=password, resource=resource):
        return error("could not authenticate to server %s:%s" % (server, port),
                     EXIT_SEND_FAILED)

    recipients = opts.recipients
    if not recipients:
        recipients = [user for user in client.getRoster().keys() if user != username]
    for user in recipients:
        client.send(Message(user, message))
    print("XMPP notification sent to %s" % ", ".join(recipients))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
