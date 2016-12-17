#!/usr/bin/env python3

USAGE = """Usage: {} existing

    existing: Name of the file exported by Anki

This script uses the "existing" file as a list of cards already imported into 
Anki. It reads additional import data from stdin, and writes the complete 
output to stdout. 
"""

import sys
try:
    existingfilepath = sys.argv[1]
except:
    print(USAGE.format(sys.argv[0]))
    sys.exit(1)

# Read the "existing" file to find all tags already associated to each known 
# student ID number. 
import csv
students = {}
with open(existingfilepath, newline="", encoding="ascii") as existingfile:
    csvreader = csv.reader(existingfile, delimiter="\t", quotechar="'")
    for studentid, url, name, foo, bar, bat, tags in csvreader:
        students[studentid] = tags

# Now read all the import data from stdin and create the output to write out. 
# (For efficiency, we assume the input data has already been sorted.) 
lastline = None
for line in sys.stdin:
    line = line.rstrip()
    if lastline and lastline[:11] == line[:11]:
        lastline += " " + line.split(";")[3]
    else:
        if lastline:
            print(lastline)
        lastline = line
        try:
            lastline += " " + students[lastline[:11]]
        except KeyError:
            pass
print(lastline)

