"""Small Python 3 argparse adapter for Shinken's historical CLI surface."""

from __future__ import annotations

import argparse
from types import SimpleNamespace


def _convert_type(value):
    if value in (None, "string"):
        return None
    if value == "int":
        return int
    if value == "float":
        return float
    return value


def _convert_help(text):
    """Convert an optparse help text to the argparse syntax.

    optparse expands ``%default`` and ``%prog`` and prints other ``%``
    signs literally; argparse uses ``%(default)s``/``%(prog)s`` and
    requires a literal ``%`` to be written ``%%``.
    """
    if not isinstance(text, str):
        return text
    marker_default, marker_prog = '\0DEFAULT\0', '\0PROG\0'
    text = text.replace('%default', marker_default).replace('%prog', marker_prog)
    text = text.replace('%', '%%')
    return text.replace(marker_default, '%(default)s').replace(marker_prog, '%(prog)s')


class OptionParser(argparse.ArgumentParser):
    """Accept the subset of optparse used by bundled Shinken commands."""

    def __init__(self, usage=None, version=None, *args, **kwargs):
        if usage:
            usage = usage.replace("%prog", "%(prog)s")
        super().__init__(usage=usage, add_help=False, *args, **kwargs)
        self.add_argument('-h', '--help', action='help', help='Show this help message and exit')
        if version:
            self.add_argument("--version", action="version", version=version.replace("%prog", "%(prog)s"))

    def add_option(self, *option_strings, **kwargs):
        kwargs = dict(kwargs)
        if 'help' in kwargs:
            kwargs['help'] = _convert_help(kwargs['help'])
        option_type = kwargs.pop("type", None)
        if option_type == "choice":
            kwargs["type"] = str
        else:
            converted = _convert_type(option_type)
            if converted is not None:
                kwargs["type"] = converted
        return self.add_argument(*option_strings, **kwargs)

    def add_option_group(self, group):
        return group

    def parse_args(self, args=None, values=None):
        namespace, extras = super().parse_known_args(args)
        return namespace, extras


class OptionGroup:
    def __init__(self, parser, title, description=None):
        self.parser = parser

    def add_option(self, *option_strings, **kwargs):
        return self.parser.add_option(*option_strings, **kwargs)


Values = SimpleNamespace


class _Namespace:
    OptionParser = OptionParser
    OptionGroup = OptionGroup
    Values = Values


optparse = _Namespace()
