#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Compatibility helpers for Shinken's legacy Pyro call sites using Pyro5."""

from __future__ import annotations

from typing import Optional

from Pyro5 import api as pyro_api

# Shinken's existing daemon payloads rely on pickle serialization.
pyro_api.config.SERIALIZER = "pickle"
pyro_api.config.SERIALIZERS_ACCEPTED.add("pickle")


class Pyro:
    """Expose the historic namespace-style URI/Proxy accessors."""

    URI = pyro_api.URI
    Proxy = pyro_api.Proxy


def create_uri(address: str, port: int | str, object_name: str, use_ssl: bool) -> pyro_api.URI:
    """Build a Pyro5 URI for a Shinken daemon endpoint."""

    pyro_api.config.SSL = use_ssl
    return pyro_api.URI(f"PYRO:{object_name}@{address}:{port}")


def getProxy(
    uri: pyro_api.URI | str,
    hmac_key: Optional[str] = None,
    timeout: Optional[float] = None,
) -> pyro_api.Proxy:
    """Create a Pyro5 proxy while preserving legacy HMAC/timeout behavior."""

    proxy = pyro_api.Proxy(uri)
    if hmac_key:
        proxy._pyroHmacKey = hmac_key.encode("utf-8")
    if timeout is not None:
        proxy._pyroTimeout = timeout
    return proxy
