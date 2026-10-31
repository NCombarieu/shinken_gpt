#!/usr/bin/env python
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

"""Dateranges with a fixed date in the past.

Python 2 silently evaluated ``timestamp < None`` as False. Under Python 3
the same comparison raised ``TypeError`` and crashed the scheduler with
dated holidays. These tests run without any monkeypatch of the production
code.
"""

import time
import unittest

import shinken_test  # noqa: F401  (sets up sys.path)
from shinken.objects.timeperiod import Timeperiod


def _tp(*dateranges):
    t = Timeperiod()
    t.timeperiod_name = ''
    for entry in dateranges:
        t.resolve_daterange(t.dateranges, entry)
    return t


class TestDaterangePastDates(unittest.TestCase):

    def setUp(self):
        self.ref = time.mktime(time.strptime("12 Jul 2010 15:00:00", "%d %b %Y %H:%M:%S"))

    def test_past_calendar_date_has_no_next_valid_time(self):
        dr = _tp('2010-01-01 - 2010-02-01 00:00-24:00').dateranges[0]
        self.assertIsNone(dr.get_next_valid_time_from_t(self.ref))
        self.assertIsNone(dr.get_next_valid_day(self.ref))

    def test_past_calendar_date_with_weekday(self):
        t = _tp('2010-01-01 - 2010-02-01 00:00-24:00', 'monday 08:00-17:00')
        # Monday 12 Jul 2010 15:00 is valid thanks to the weekday entry
        self.assertEqual(self.ref, t.get_next_valid_time_from_t(self.ref))
        evening = self.ref + 4 * 3600
        nxt = t.get_next_valid_time_from_t(evening)
        self.assertEqual("Mon Jul 19 08:00:00 2010", time.asctime(time.localtime(nxt)))

    def test_past_calendar_date_next_invalid_time(self):
        dr = _tp('2010-01-01 - 2010-02-01 00:00-24:00').dateranges[0]
        # Outside the daterange: the reference itself is invalid
        self.assertEqual(self.ref, dr.get_next_invalid_time_from_t(self.ref))
        t = _tp('2010-01-01 - 2010-02-01 00:00-24:00')
        self.assertEqual(self.ref, t.get_next_invalid_time_from_t(self.ref))

    def test_holiday_exclusion_in_the_past(self):
        workhours = _tp('monday 00:00-24:00')
        holidays = _tp('2010-07-05 00:00-24:00')
        workhours.exclude = [holidays]
        nxt = workhours.get_next_valid_time_from_t(self.ref + 10 * 3600)
        self.assertEqual("Mon Jul 19 00:00:00 2010", time.asctime(time.localtime(nxt)))


if __name__ == '__main__':
    unittest.main()
