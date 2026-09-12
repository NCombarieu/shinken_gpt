#!/usr/bin/env python3

import json
import sys

print("Argv", sys.argv)

# Case 1 means host0 is the father of host1.
if sys.argv[1] == 'case1':
    data = [[["host", "test_host_0"], ["host", "test_host_1"]]]
elif sys.argv[1] == 'case2':
    data = [[["host", "test_host_2"], ["host", "test_host_1"]]]
else:
    raise SystemExit("unknown dependency test case: %s" % sys.argv[1])

with open(sys.argv[2], 'w', encoding='utf-8') as output:
    json.dump(data, output)
