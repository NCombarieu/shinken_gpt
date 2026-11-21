#!/usr/bin/env python3
# Copyright (C) 2012:
#    Romain Forlot, rforlot@yahoo.com
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.
"""Send a Shinken host or service notification by e-mail.

The message is built with :class:`email.message.EmailMessage` and delivered
through an SMTP relay (``-S/--smtp-server``, ``--smtp-port``, optional
STARTTLS or implicit TLS and authentication), or through the local
``sendmail`` binary when ``-S None`` is given.

Exit codes: 0 on success, 2 when the message could not be delivered,
3 on invalid arguments or unreadable password file.
"""

from __future__ import annotations

import argparse
import getpass
import html
import logging
import mimetypes
import os
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.parse
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

EXIT_OK = 0
EXIT_SEND_FAILED = 2
EXIT_USAGE = 3

MAIL_WELCOME = "Shinken Monitoring System Notification"
SENDMAIL = "/usr/sbin/sendmail"

HTML_STYLE = """\
body {font-family: Verdana, sans-serif; font-size: 10pt;}
table {margin-left: auto; margin-right: auto; border-collapse: collapse;}
th, td {font-family: Verdana, sans-serif; font-size: 10pt; text-align: left;
        padding: 2px 6px;}
th {white-space: nowrap;}
th.title {background-color: #004488; color: #ffffff;}
tr.odd th, tr.odd td {background-color: #F2F2F2;}
tr.even th {background-color: #D9D9D9;}
tr.even td {background-color: #FFFFFF;}
"""

log = logging.getLogger("notify_by_email")


class UsageError(Exception):
    """Invalid or inconsistent command line options."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Notify Shinken host or service alerts by e-mail through an SMTP relay.",
    )
    debug = parser.add_argument_group("Debugging and test options")
    debug.add_argument("-D", "--debug", action="store_true", help="Enable debug logging")
    debug.add_argument("-t", "--test", action="store_true",
                       help="Send a test message with dummy macro values")
    debug.add_argument("-l", "--logfile", help="Log to this file instead of stderr")

    general = parser.add_argument_group("General options")
    general.add_argument("-f", "--format", choices=("txt", "html"), default="html",
                         help="Mail format (default: html, with a plain text alternative)")
    general.add_argument("-r", "--receivers",
                         help="Comma-separated list of recipients (e.g. $CONTACTEMAIL$)")
    general.add_argument("-s", "-F", "--sender", dest="sender",
                         help="Sender address (default: <current user>@<fqdn>)")
    general.add_argument("-p", "--prefix", default="", help="Subject prefix")

    smtp = parser.add_argument_group("SMTP relay")
    smtp.add_argument("-S", "--smtp-server", "--SMTP", dest="smtp_server", default="localhost",
                      help="SMTP relay host name; 'None' to use %s instead "
                           "(default: localhost)" % SENDMAIL)
    smtp.add_argument("--smtp-port", type=int, default=None,
                      help="SMTP relay port (default: 25, or 465 with --smtp-ssl)")
    smtp.add_argument("-T", "--smtp-starttls", action="store_true",
                      help="Upgrade the connection with STARTTLS (certificate verified)")
    smtp.add_argument("--smtp-ssl", action="store_true",
                      help="Use implicit TLS (SMTPS, usually port 465)")
    smtp.add_argument("--smtp-timeout", type=float, default=30.0,
                      help="Network timeout in seconds (default: 30)")
    smtp.add_argument("-U", "--smtp-user", help="SMTP user name for authentication")
    smtp.add_argument("--smtp-password-file",
                      help="File containing the SMTP password (first line is used)")
    smtp.add_argument("-P", "--smtp-password", help=argparse.SUPPRESS)

    shinken = parser.add_argument_group(
        "Shinken macros",
        "When -c/-o are not given, values are read from the NAGIOS_* environment "
        "macros (requires enable_environment_macros=1).")
    shinken.add_argument("-n", "--notification-object", choices=("host", "service"),
                         default="host", help="Notified object type (default: host)")
    shinken.add_argument("-c", "--commonmacros",
                         help='"$NOTIFICATIONTYPE$,,$HOSTNAME$,,$HOSTADDRESS$,,$LONGDATETIME$"')
    shinken.add_argument("-o", "--objectmacros",
                         help='service: "$SERVICEDESC$,,$SERVICESTATE$,,$SERVICEOUTPUT$,,'
                              '$SERVICEDURATION$" ; host: "$HOSTSTATE$,,$HOSTDURATION$"')
    shinken.add_argument("-d", "--detailleddesc", help="$_SERVICEDETAILLEDESC$ custom macro")
    shinken.add_argument("-i", "--impact", help="$_SERVICEIMPACT$ custom macro")
    shinken.add_argument("-a", "--action", dest="fixaction",
                         help="$_SERVICEFIXACTIONS$ custom macro")

    webui = parser.add_argument_group("Web interface link")
    webui.add_argument("-u", "--url", dest="webui_url",
                       help="Base URL of the web interface; a link to the object is added")
    webui.add_argument("-w", "--webui", action="store_true",
                       help="Kept for compatibility; the link is added when -u is given")
    webui.add_argument("--logo", help="Image embedded at the top of the HTML message")
    return parser


def _split(value: str | None, count: int) -> list[str]:
    parts = (value or "").split(",,")
    parts += [""] * (count - len(parts))
    return parts[:count]


def collect_fields(opts) -> tuple[dict, dict]:
    """Return (common, object) ordered dicts of label -> value."""
    if opts.test:
        common = {
            "Notification type": "TEST",
            "Hostname": "shinken",
            "Host address": "127.0.0.1",
            "Date": formatdate(localtime=True),
        }
        if opts.notification_object == "service":
            obj = {
                "Service description": "Test_Service",
                "Service state": "TEST",
                "Service output": "This is a test notification.",
                "Service state duration": "00h 00m 10s",
            }
        else:
            obj = {"Host state": "TEST", "Host state duration": "00h 00m 20s"}
        return common, obj

    env = os.environ.get
    if opts.commonmacros is None:
        values = [env("NAGIOS_NOTIFICATIONTYPE", ""), env("NAGIOS_HOSTNAME", ""),
                  env("NAGIOS_HOSTADDRESS", ""), env("NAGIOS_LONGDATETIME", "")]
    else:
        values = _split(opts.commonmacros, 4)
    common = dict(zip(("Notification type", "Hostname", "Host address", "Date"), values))

    if opts.notification_object == "service":
        labels = ("Service description", "Service state", "Service output",
                  "Service state duration")
        if opts.objectmacros is None:
            values = [env("NAGIOS_SERVICEDESC", ""), env("NAGIOS_SERVICESTATE", ""),
                      env("NAGIOS_SERVICEOUTPUT", ""), env("NAGIOS_SERVICEDURATION", "")]
        else:
            values = _split(opts.objectmacros, 4)
    else:
        labels = ("Host state", "Host state duration")
        if opts.objectmacros is None:
            values = [env("NAGIOS_HOSTSTATE", ""), env("NAGIOS_HOSTDURATION", "")]
        else:
            values = _split(opts.objectmacros, 2)
    obj = dict(zip(labels, values))
    return common, obj


def build_subject(opts, common: dict, obj: dict) -> str:
    if opts.notification_object == "service":
        subject = "%s on Host: %s about service %s since %s" % (
            obj["Service state"], common["Hostname"], obj["Service description"],
            obj["Service state duration"])
    else:
        subject = "Host %s alert for %s since %s" % (
            obj["Host state"], common["Hostname"], obj["Host state duration"])
    return opts.prefix + subject


def build_url(opts, common: dict, obj: dict) -> str | None:
    if not opts.webui_url:
        return None
    quote = urllib.parse.quote
    url = "%s/%s/%s" % (opts.webui_url.rstrip("/"), opts.notification_object,
                        quote(common["Hostname"], safe=""))
    if opts.notification_object == "service":
        url += "/" + quote(obj["Service description"], safe="")
    return url


def default_sender() -> str:
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "shinken"
    return "%s@%s" % (user, socket.getfqdn())


def build_message(opts, receivers: list[str]) -> EmailMessage:
    common, obj = collect_fields(opts)
    fields = dict(common)
    fields.update(obj)
    if opts.detailleddesc:
        fields["Detailled description"] = opts.detailleddesc
    if opts.impact:
        fields["Impact"] = opts.impact
    if opts.fixaction:
        fields["Fix actions"] = opts.fixaction
    url = build_url(opts, common, obj)

    msg = EmailMessage()
    msg["Subject"] = build_subject(opts, common, obj)
    sender = opts.sender or default_sender()
    msg["From"] = sender
    msg["To"] = ", ".join(receivers)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2].strip("<> ") or None)
    msg["X-Shinken-Notification"] = "%s %s" % (opts.notification_object,
                                                common.get("Notification type", ""))

    text = [MAIL_WELCOME, ""]
    text += ["%s: %s" % (key, value) for key, value in fields.items()]
    if url:
        text += ["", "More details on: %s" % url]
    msg.set_content("\n".join(text) + "\n")

    if opts.format == "html":
        logo_cid = None
        if opts.logo:
            if os.path.isfile(opts.logo):
                logo_cid = make_msgid()
            else:
                log.warning("Logo file %s not found, ignored", opts.logo)
        rows = []
        for index, (key, value) in enumerate(fields.items()):
            rows.append('<tr class="%s"><th>%s</th><td>%s</td></tr>' % (
                "odd" if index % 2 == 0 else "even", html.escape(key), html.escape(str(value))))
        body = [
            "<!DOCTYPE html>",
            '<html><head><meta charset="utf-8"><style type="text/css">',
            HTML_STYLE,
            "</style></head><body>",
        ]
        if logo_cid:
            body.append('<img alt="logo" src="cid:%s">' % logo_cid[1:-1])
        body.append('<table><tr><th class="title" colspan="2">%s</th></tr>' % MAIL_WELCOME)
        body += rows
        body.append("</table>")
        if url:
            safe_url = html.escape(url, quote=True)
            body.append('<p>More details on: <a href="%s">%s</a></p>' % (safe_url, safe_url))
        body.append("</body></html>")
        msg.add_alternative("\n".join(body) + "\n", subtype="html")
        if logo_cid:
            ctype, _ = mimetypes.guess_type(opts.logo)
            maintype, subtype = (ctype or "image/png").split("/", 1)
            with open(opts.logo, "rb") as handle:
                msg.get_payload()[1].add_related(handle.read(), maintype=maintype,
                                                 subtype=subtype, cid=logo_cid)
    return msg


def read_password(opts) -> str | None:
    if opts.smtp_password_file:
        try:
            with open(opts.smtp_password_file, encoding="utf-8") as handle:
                return handle.readline().rstrip("\r\n")
        except OSError as exp:
            raise UsageError("cannot read SMTP password file %s: %s"
                             % (opts.smtp_password_file, exp.strerror)) from exp
    if opts.smtp_password:
        log.warning("-P/--smtp-password exposes the password in the process list; "
                    "use --smtp-password-file instead")
        return opts.smtp_password
    return None


def send_smtp(opts, msg: EmailMessage, receivers: list[str], password: str | None) -> None:
    port = opts.smtp_port or (465 if opts.smtp_ssl else 25)
    context = ssl.create_default_context()
    log.debug("Connecting to %s:%d", opts.smtp_server, port)
    if opts.smtp_ssl:
        client = smtplib.SMTP_SSL(opts.smtp_server, port, timeout=opts.smtp_timeout,
                                  context=context)
    else:
        client = smtplib.SMTP(opts.smtp_server, port, timeout=opts.smtp_timeout)
    with client:
        client.ehlo_or_helo_if_needed()
        if opts.smtp_starttls:
            client.starttls(context=context)
            client.ehlo()
        if opts.smtp_user:
            client.login(opts.smtp_user, password or "")
        refused = client.send_message(msg, to_addrs=receivers)
    if refused:
        # At least one recipient was accepted, otherwise send_message raised.
        log.warning("Some recipients were refused: %s", ", ".join(sorted(refused)))


def send_sendmail(opts, msg: EmailMessage) -> None:
    proc = subprocess.run([SENDMAIL, "-t", "-oi"], input=msg.as_bytes(),
                          capture_output=True, timeout=opts.smtp_timeout, check=False)
    if proc.returncode != 0:
        raise OSError("%s exited with status %d: %s" % (
            SENDMAIL, proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))


def setup_logging(opts) -> None:
    level = logging.DEBUG if opts.debug else logging.INFO
    kwargs = {"level": level, "format": "%(asctime)s:%(levelname)s: %(message)s"}
    if opts.logfile:
        kwargs["filename"] = opts.logfile
    logging.basicConfig(**kwargs)


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    setup_logging(opts)

    receivers = [r.strip() for r in (opts.receivers or "").split(",") if r.strip()]
    if not receivers:
        log.error("No recipient: use -r/--receivers (is $CONTACTEMAIL$ empty?)")
        return EXIT_USAGE
    try:
        password = read_password(opts)
        if opts.smtp_starttls and opts.smtp_ssl:
            raise UsageError("--smtp-starttls and --smtp-ssl are mutually exclusive")
        msg = build_message(opts, receivers)
    except UsageError as exp:
        log.error("%s", exp)
        return EXIT_USAGE
    except (ValueError, IndexError) as exp:
        log.error("Cannot build the message: %s", exp)
        return EXIT_USAGE

    try:
        if opts.smtp_server == "None":
            send_sendmail(opts, msg)
            target = SENDMAIL
        else:
            send_smtp(opts, msg, receivers, password)
            target = "%s:%s" % (opts.smtp_server, opts.smtp_port or (465 if opts.smtp_ssl else 25))
    except (OSError, smtplib.SMTPException, subprocess.SubprocessError) as exp:
        log.error("Failed to send notification to %s via %s: %s: %s",
                  ", ".join(receivers), opts.smtp_server, type(exp).__name__, exp)
        return EXIT_SEND_FAILED
    log.info("Mail sent to %s via %s", ", ".join(receivers), target)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
