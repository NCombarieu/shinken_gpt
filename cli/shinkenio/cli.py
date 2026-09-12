#!/usr/bin/env python3

# Copyright (C) 2009-2014:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import io
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
from urllib.parse import urlencode

import pycurl

from shinken.log import cprint, logger


# Will be populated by the shinken CLI command.
CONFIG = None


def read_package_json(fd):
    try:
        buf = fd.read()
    finally:
        fd.close()
    if isinstance(buf, bytes):
        buf = buf.decode("utf8", "ignore")
    try:
        package_json = json.loads(buf)
    except ValueError as exp:
        logger.error("Bad package.json file : %s", exp)
        sys.exit(2)
    if not package_json:
        logger.error("Bad package.json file")
        sys.exit(2)
    return package_json


def _archive_filter(tarinfo):
    name = tarinfo.name
    if name.startswith("./.git") or name.startswith(".git") or name.endswith("~"):
        return None
    return tarinfo


def create_archive(to_pack):
    to_pack = os.path.abspath(to_pack)
    if not os.path.exists(to_pack):
        logger.error("Error : the directory to pack is missing %s", to_pack)
        sys.exit(2)
    package_json_p = os.path.join(to_pack, "package.json")
    if not os.path.exists(package_json_p):
        logger.error("Error : Missing file %s", package_json_p)
        sys.exit(2)
    package_json = read_package_json(open(package_json_p, encoding="utf-8"))
    name = package_json.get("name")
    if not name:
        logger.error("Missing name entry in the package.json file. Cannot pack")
        sys.exit(2)

    tmp_file = os.path.join(tempfile.gettempdir(), name + ".tar.gz")
    with tarfile.open(tmp_file, "w:gz") as tar:
        tar.add(to_pack, arcname=".", filter=_archive_filter)
    logger.debug("Saved file %s", tmp_file)
    return tmp_file


def _curl_buffer():
    return io.BytesIO()


def _decode_response(response):
    value = response.getvalue()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _configure_curl(curl, timeout=300):
    proxy = CONFIG["shinken.io"]["proxy"]
    proxy_socks5 = CONFIG["shinken.io"]["proxy_socks5"]
    curl.setopt(curl.CONNECTTIMEOUT, 30)
    curl.setopt(curl.TIMEOUT, timeout)
    if proxy:
        curl.setopt(curl.PROXY, proxy)
    if proxy_socks5:
        curl.setopt(curl.PROXY, proxy_socks5)
        curl.setopt(curl.PROXYTYPE, curl.PROXYTYPE_SOCKS5)


def publish_archive(archive):
    api_key = CONFIG["shinken.io"]["api_key"]
    c = pycurl.Curl()
    c.setopt(c.POST, 1)
    _configure_curl(c)
    c.setopt(c.URL, "http://shinken.io/push")
    c.setopt(
        c.HTTPPOST,
        [
            ("api_key", api_key),
            (
                "data",
                (c.FORM_FILE, str(archive), c.FORM_CONTENTTYPE, "application/x-gzip"),
            ),
        ],
    )
    response = _curl_buffer()
    c.setopt(pycurl.WRITEFUNCTION, response.write)
    try:
        c.perform()
    except pycurl.error as exp:
        logger.error("There was a critical error : %s", exp)
        sys.exit(2)
    status_code = c.getinfo(pycurl.HTTP_CODE)
    c.close()
    response_text = _decode_response(response)
    if status_code != 200:
        logger.error("There was a critical error : %s", response_text)
        sys.exit(2)
    ret = json.loads(response_text.replace("\\/", "/"))
    if ret.get("status") == 200:
        logger.info(ret.get("text"))
    else:
        logger.error(ret.get("text"))
        sys.exit(2)


def do_publish(to_pack="."):
    publish_archive(create_archive(to_pack))


def search(look_at):
    c = pycurl.Curl()
    c.setopt(c.POST, 0)
    _configure_curl(c)
    args = {"keywords": ",".join(look_at)}
    c.setopt(c.URL, "shinken.io/searchcli?" + urlencode(args))
    response = _curl_buffer()
    c.setopt(pycurl.WRITEFUNCTION, response.write)
    try:
        c.perform()
    except pycurl.error as exp:
        logger.error("There was a critical error : %s", exp)
        return []
    status_code = c.getinfo(pycurl.HTTP_CODE)
    c.close()
    response_text = _decode_response(response)
    if status_code != 200:
        logger.error("There was a critical error : %s", response_text)
        return []
    ret = json.loads(response_text.replace("\\/", "/"))
    result = ret.get("result")
    if ret.get("status") != 200:
        logger.info(result)
        return []
    return result


def print_search_matches(matches):
    if not matches:
        logger.warning("No match found in shinken.io")
        return
    packages = {package["name"]: package for package in matches}
    for name in sorted(packages):
        package = packages[name]
        cprint("%s " % name, "green", end="")
        cprint(
            "(%s) [%s] : %s"
            % (
                package["user_id"],
                ",".join(package["keywords"]),
                package["description"],
            )
        )


def do_search(*look_at):
    if look_at == ("all",):
        matches = search(("pack",)) + search(("module",))
    else:
        matches = search(look_at)
    if not matches:
        print('you are unlucky, use "shinken search all" for a complete list')
    print_search_matches(matches)


def inventor(look_at):
    inventory = CONFIG["paths"]["inventory"]
    for package_name in os.listdir(inventory):
        package_dir = os.path.join(inventory, package_name)
        if not os.path.exists(os.path.join(package_dir, "package.json")):
            continue
        if not look_at or package_name in look_at:
            print(package_name)
        if look_at and package_name not in look_at:
            continue
        content_p = os.path.join(package_dir, "content.json")
        if not os.path.exists(content_p):
            logger.error("Missing %s file", content_p)
            continue
        try:
            with open(content_p, encoding="utf-8") as content_file:
                content = json.load(content_file)
        except (OSError, ValueError) as exp:
            logger.error('Bad %s file "%s"', content_p, exp)
            continue
        for entry in content:
            prefix = "(d)" if str(entry["type"]) == "5" else "(f)"
            print(prefix + entry["name"])


def do_inventory(*look_at):
    inventor(look_at)


def _copytree(src, dst, symlinks=False, ignore=None):
    del symlinks, ignore
    for item in os.listdir(src):
        source = os.path.join(src, item)
        destination = os.path.join(dst, item)
        if os.path.isdir(source):
            os.makedirs(destination, exist_ok=True)
            _copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def _chmodplusx(directory):
    for item in os.listdir(directory):
        path = os.path.join(directory, item)
        if os.path.isdir(path):
            _chmodplusx(path)
        else:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def grab_package(pname):
    cprint("Grabbing : ", end="")
    cprint(pname, "green")
    c = pycurl.Curl()
    c.setopt(c.POST, 0)
    _configure_curl(c)
    c.setopt(c.URL, "shinken.io/grab/%s" % pname)
    response = _curl_buffer()
    c.setopt(pycurl.WRITEFUNCTION, response.write)
    try:
        c.perform()
    except pycurl.error as exp:
        logger.error("There was a critical error : %s", exp)
        sys.exit(2)
    status_code = c.getinfo(pycurl.HTTP_CODE)
    c.close()
    if status_code != 200:
        logger.error("There was a critical error : %s", _decode_response(response))
        sys.exit(2)
    raw = response.getvalue()
    logger.debug("CURL result len : %d", len(raw))
    return raw


def grab_local(directory):
    to_pack = os.path.abspath(directory)
    if not os.path.exists(to_pack):
        raise RuntimeError("Error : the directory to install is missing %s" % to_pack)
    package_json_p = os.path.join(to_pack, "package.json")
    if not os.path.exists(package_json_p):
        logger.error("Error : Missing file %s", package_json_p)
        sys.exit(2)
    package_json = read_package_json(open(package_json_p, encoding="utf-8"))
    pname = package_json.get("name")
    if not pname:
        raise RuntimeError("Missing name entry in the package.json file. Cannot install")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(to_pack, arcname=".", filter=_archive_filter)
    return pname, buffer.getvalue()


def _safe_members(tar_file):
    for member in tar_file.getmembers():
        normalized = os.path.normpath(member.name)
        if os.path.isabs(member.name) or normalized.startswith(".."):
            raise ValueError("unsafe archive path: %s" % member.name)
        yield member


def install_package(pname, raw, update_only=False):
    if not raw:
        logger.error("The package %s cannot be found", pname)
        sys.exit(2)
    tmpdir = os.path.join(tempfile.gettempdir(), pname)
    shutil.rmtree(tmpdir, ignore_errors=True)
    os.makedirs(tmpdir)

    package_content = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tar_file:
        members = list(_safe_members(tar_file))
        for member in members:
            if member.name == ".":
                continue
            package_content.append(
                {
                    "name": member.name,
                    "mode": member.mode,
                    "type": member.type.decode("ascii") if isinstance(member.type, bytes) else member.type,
                    "size": member.size,
                }
            )
        tar_file.extractall(tmpdir, members=members)

    package_json_p = os.path.join(tmpdir, "package.json")
    if not os.path.exists(package_json_p):
        logger.error("Error : bad archive : Missing file %s", package_json_p)
        sys.exit(2)
    package_json = read_package_json(open(package_json_p, encoding="utf-8"))
    logger.debug("Package.json content %s", package_json)

    paths = CONFIG["paths"]
    modules_dir = paths["modules"]
    share_dir = paths["share"]
    packs_dir = paths["packs"]
    etc_dir = paths["etc"]
    doc_dir = paths["doc"]
    inventory_dir = paths["inventory"]
    libexec_dir = paths.get("libexec", os.path.join(paths["lib"], "libexec"))
    test_dir = paths.get("test", "/__DONOTEXISTS__")

    for directory in (modules_dir, share_dir, packs_dir, doc_dir, inventory_dir):
        if not os.path.exists(directory):
            logger.error("The installation directory %s is missing!", directory)
            sys.exit(2)

    p_share = os.path.join(tmpdir, "share")
    if os.path.exists(p_share):
        _copytree(p_share, share_dir)

    p_module = os.path.join(tmpdir, "module")
    if os.path.exists(p_module):
        mod_dest = os.path.join(modules_dir, pname)
        shutil.rmtree(mod_dest, ignore_errors=True)
        shutil.copytree(p_module, mod_dest)

    p_doc = os.path.join(tmpdir, "doc")
    if os.path.exists(p_doc):
        doc_dest = os.path.join(doc_dir, "source", "89_packages", pname)
        shutil.rmtree(doc_dest, ignore_errors=True)
        shutil.copytree(p_doc, doc_dest)

    if not update_only:
        p_pack = os.path.join(tmpdir, "pack")
        if os.path.exists(p_pack):
            pack_dest = os.path.join(packs_dir, pname)
            shutil.rmtree(pack_dest, ignore_errors=True)
            shutil.copytree(p_pack, pack_dest)
        p_etc = os.path.join(tmpdir, "etc")
        if os.path.exists(p_etc):
            _copytree(p_etc, etc_dir)

    p_tests = os.path.join(tmpdir, "test")
    if os.path.exists(p_tests) and os.path.exists(test_dir):
        _copytree(p_tests, test_dir)

    p_libexec = os.path.join(tmpdir, "libexec")
    if os.path.exists(p_libexec) and os.path.exists(libexec_dir):
        _chmodplusx(p_libexec)
        _copytree(p_libexec, libexec_dir)

    p_inv = os.path.join(inventory_dir, pname)
    os.makedirs(p_inv, exist_ok=True)
    shutil.copy2(package_json_p, os.path.join(p_inv, "package.json"))
    with open(os.path.join(p_inv, "content.json"), "w", encoding="utf-8") as content_file:
        json.dump(package_content, content_file)

    shutil.rmtree(tmpdir, ignore_errors=True)
    cprint("OK ", "green", end="")
    cprint(pname)


def do_install(pname="", local=False, download_only=False):
    if local:
        pname, raw = grab_local(pname)
    else:
        if not pname:
            logger.error("Please select a package to install")
            return
        raw = grab_package(pname)

    if download_only:
        tmpf = os.path.join(tempfile.gettempdir(), pname + ".tar.gz")
        try:
            with open(tmpf, "wb") as target:
                target.write(raw)
            cprint("Download OK: %s" % tmpf, "green")
        except OSError as exp:
            logger.error("Package save fail: %s", exp)
            sys.exit(2)
        return
    install_package(pname, raw)


def do_update(pname, local=False):
    if local:
        pname, raw = grab_local(pname)
    else:
        raw = grab_package(pname)
    install_package(pname, raw, update_only=True)


exports = {
    do_publish: {
        "keywords": ["publish"],
        "args": [
            {
                "name": "to_pack",
                "default": ".",
                "description": "Package directory. Default to .",
            }
        ],
        "description": "Publish a package on shinken.io. Valid api key required",
    },
    do_search: {
        "keywords": ["search"],
        "args": [],
        "description": "Search a package on shinken.io by looking at its keywords",
    },
    do_install: {
        "keywords": ["install"],
        "args": [
            {"name": "pname", "description": "Package to install"},
            {
                "name": "--local",
                "description": "Use a local directory instead of the shinken.io version",
                "type": "bool",
            },
            {
                "name": "--download-only",
                "description": "Only download the package",
                "type": "bool",
            },
        ],
        "description": "Grab and install a package from shinken.io",
    },
    do_update: {
        "keywords": ["update"],
        "args": [
            {"name": "pname", "description": "Package to update"},
            {
                "name": "--local",
                "description": "Use a local directory instead of the shinken.io version",
                "type": "bool",
            },
        ],
        "description": "Grab and update a package from shinken.io without replacing configuration",
    },
    do_inventory: {
        "keywords": ["inventory"],
        "args": [],
        "description": "List locally installed packages",
    },
}
