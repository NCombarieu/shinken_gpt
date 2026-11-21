from __future__ import absolute_import

import os

from shinken_test import ShinkenTest


class TestConfig(ShinkenTest):

    def setUp(self):
        pass  # force no setUp for this class.

    def assert_configuration_message(self, messages, expected_text, filename, line):
        expected_suffix = "%s:%d" % (os.path.join('test', 'etc', filename), line)
        matching = [message for message in messages if expected_text in message]
        self.assertTrue(matching, "%r not found in %r" % (expected_text, messages))
        self.assertTrue(
            any(message.replace('\\', '/').endswith(expected_suffix.replace('\\', '/'))
                for message in matching),
            "expected source %r in %r" % (expected_suffix, matching),
        )

    def test_bad_template_use_itself(self):
        self.setup_with_file('etc/bad_template_use_itself.cfg')
        self.assert_configuration_message(
            self.conf.hosts.configuration_errors,
            "Host 'bla' use/inherits from itself ! Imported from:",
            'bad_template_use_itself.cfg',
            1,
        )

    def test_bad_host_use_undefined_template(self):
        self.setup_with_file('etc/bad_host_use_undefined_template.cfg')
        self.assert_configuration_message(
            self.conf.hosts.configuration_warnings,
            "Host 'bla' use/inherit from an unknown template ('undefined') ! Imported from:",
            'bad_host_use_undefined_template.cfg',
            2,
        )
