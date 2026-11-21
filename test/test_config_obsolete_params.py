"""Obsolete Nagios parameters are only reported when the admin wrote them."""

import logging

from shinken.objects.config import Config


def _config(params):
    conf = Config()
    conf.load_params(params)
    super(Config, conf).fill_default()  # only the global parameters
    return conf


def test_no_notice_for_parameters_left_to_default(caplog):
    conf = _config(['interval_length=60'])
    with caplog.at_level(logging.DEBUG):
        conf.notice_about_useless_parameters()
        conf.warn_about_unmanaged_parameters()
    assert 'useless' not in caplog.text
    assert 'Unmanaged' not in caplog.text


def test_notice_for_obsolete_parameter_written_by_admin(caplog):
    conf = _config(['sleep_time=0.25', 'use_regexp_matching=1'])
    with caplog.at_level(logging.DEBUG):
        conf.notice_about_useless_parameters()
        conf.warn_about_unmanaged_parameters()
    assert 'The parameter sleep_time is useless' in caplog.text
    assert 'use_regexp_matching' in caplog.text
    assert 'interval_length' not in caplog.text
