#!/usr/bin/env python3
DESCRIPTION = "Download photos and set up text file for Anki import"
EPILOG = """
Each downloaded photo will be named "UCLA_Student_xxx-xxx-xxx.jpg", where the 
x's are the student's 9-digit student ID number. If a file with that name 
already exists, the downloaded photo will be compared to the existing one. In 
the rare case that they are *not* identical (meaning a student who was already 
in the collection apparently got a new student ID photo) the old one will be 
renamed with a suffix, and the newly downloaded one will replace it. 

As the photo files are downloaded, an Anki import file (text format) will be 
created, in the same directory as the CSV file, with the same name as the CSV 
file, except that the .csv suffix will be repaced with .Anki_Import.txt. 

So the basic steps that should be necessary to import student flashcards into 
Anki are as follows: 
    1. Download the roster for your class as a CSV file from my.ucla. 
    2. While signed in to my.ucla in Firefox, use the "Export Cookies" add-on 
       to export your cookies to a cookies.txt file. 
    3. *While still signed in to my.ucla*, run this script on the CSV file you 
       downloaded, and using the cookies.txt file you just exported. 
    4. In Anki, import the text file that the script created. 
That's it! 
"""

import sys
import os
import argparse
import subprocess
import re
import csv
import filecmp

parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, 
        formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("-d", "--download-only", action="store_true", 
    help="Only download photos. Do not create text file for import.")
parser.add_argument("-t", "--textfile-only", action="store_true", 
    help="Only create the text file for import. Do not download photos.")
parser.add_argument("-e", "--existing", action="store", 
    help="Text file (tab separated) containing the existing names from " + 
        "Anki. If this is given, any student ID numbers from the new roster " + 
        "that match existing entries will be merged together with the data " + 
        "from the existing entries (particularly the tags). In case of " + 
        "conflicts, the user will be prompted.")
parser.add_argument("csvfilepath", 
    help="Name of the CSV file containing the student roster, as downloaded " + 
        "from my.ucla")
parser.add_argument("classindex", type=int, 
    help="The index of this class in the list of this instructor's classes " + 
        "for the given term, starting from 0. In other words, if this is " + 
        "your only class this quarter, this number should be a 0. If you " + 
        "are teaching three classes this quarter, then the first one in the " + 
        "list on my.ucla (which seems to be alphabetical by department/" + 
        "course number/section) would be 0, the second one would be 1, and " + 
        "the last one would be 2.")
parser.add_argument("ankipath", 
    help="The path to your Anki directory. The photo files will be " + 
        'downloaded and saved into the "collection.media" subdirectory of ' + 
        "this directory, ready for import. If you instead specify another " + 
        'directory for this, that does not have a "collection.media" ' + 
        "subdirectory, then the photos will be downloaded to that directory.")
parser.add_argument("cookiespath", nargs="?", 
    default="cookies.txt", help="The path to a cookies.txt file containing " + 
        "the cookies for a currently logged-in my.ucla session. If not " + 
        "specified, this defaults to a file named cookies.txt, in the " + 
        "current directory.")
args = parser.parse_args()

#NAMEFORMAT = re.compile(r'(?P<lastname>[^,]+)(,\s+(?P<firstname>\S+)(\s+(?P<middlename>[^,(]+))?(,\s+(?P<suffix>\S+))?)?(\s+[(](P<realname>.*)[)])?')
PARENSFORMAT = re.compile(r'(.*)[(](.*)[)](.*)')
def name_case(name):
    "Take a single (possibly hyphenated) word from a name and change its case"

    def name_case_hyphenated(name):
        if name in ("de", "el", "la", "los", "las"):
            return name
        return "-".join([name_case_word(word) for word in name.split("-")])
    def name_case_word(name):
        name = name[:1].upper() + name[1:]    # No, I don't mean to use title()
        if name[:2] in ("Mc", "O'", "D'"):
            name = name[:2] + name[2:3].upper() + name[3:]
        return name
    return " ".join([name_case_hyphenated(word) for word in name.split()])

def format_name(name):
    name = name.lower()
    match = PARENSFORMAT.match(name)
    if match:
        name, realfirstname, junk = match.groups()
        realfirstname = name_case(realfirstname)
        if junk:
            raise ValueError("Unexpected characters after parentheses in " + 
                    "name {}".format(name.upper()))
    else:
        realfirstname = ""
    components = name.split(", ")
    if len(components) > 3:
        raise ValueError("Too many components in name {}".format(name.upper()))
    if len(components) == 3:
        suffix = components[2].upper()
        if suffix == "JR" or suffix == "SR":
            suffix = suffix.title()
    else:
        suffix = ""
    if len(components) >= 2:
        if realfirstname:
            firstname = name_case(components[1])
            middlename = ""
        else:
            firstname, junk, middlename = components[1].partition(" ")
            firstname = name_case(firstname)
            middlename = name_case(middlename)
            realfirstname = firstname
    else:
        firstname = middlename = ""
    lastname = name_case(components[0])
    if firstname:
        preferredname = "{} {}".format(firstname, lastname)
    else:
        preferredname = lastname
    fullname = " ".join(filter(None, 
        (realfirstname, middlename, lastname, suffix)))
    return preferredname, fullname

# Generate the name of the Anki import file from the name of the CSV file
if args.download_only:
    ankifilepath = os.devnull
elif args.csvfilepath.lower()[-4:] == ".csv":
    ankifilepath = args.csvfilepath[:-4] + ".Anki_Import.txt"
else:
    ankifilepath = args.csvfilepath + ".Anki_Import.txt"

# Get the name of the directory to download to, if applicable
if not args.textfile_only:
    downloaddir = os.path.join(args.ankipath, "collection.media")
    if not os.path.isdir(downloaddir):
        downloaddir = args.ankipath
        if not os.path.isdir(downloaddir):
            print("ERROR: {} is not a directory.".format(downloaddir))
            sys.exit(1)

# Load the existing Anki data, if given
existing_students = {}
if args.existing and not args.download_only:
    with open(args.existing, newline="", encoding="ascii") as existingfile:
        csvreader = csv.reader(existingfile, delimiter="\t", quotechar="'")
        for studentid, url, prefname, fullname, foo, bar, tags in csvreader:
            existing_students[studentid] = (prefname, fullname, tags)

# Read the given .CSV file to find names and ID numbers of students. As we find 
# them, create the text file that Anki will import. 
TERMABBREVS = {"W": "Winter", "S": "Spring", "1": "Summer", "F": "Fall"}
downloads = []
with open(args.csvfilepath, newline="", encoding="ascii") as csvfile, open(
        ankifilepath, "w", encoding="ascii") as ankifile:
    csvreader = csv.reader(csvfile, delimiter=",", quotechar='"')
    term = next(csvreader)[0][len("Term: "):]
    classid = next(csvreader)[0][len("Class: "):].split()
    classid = classid[0] + classid[1] + "-" + classid[3]
    classid += "-" + TERMABBREVS[term[2]] + "-20" + term[:2]
    for i in range(7):
        next(csvreader)
    for line in csvreader:
        if len(line) < 2:
            continue
        studentid, studentname, *junk = line
        preferredname, fullname = format_name(studentname)
        if studentid in existing_students:
            old_preferredname, old_fullname, tags = existing_students[studentid]
            if old_preferredname != preferredname or old_fullname != fullname:
                print("WARNING: Names don't match up for {}:".format(studentid))
                if old_preferredname != preferredname:
                    print("    Preferred name was {}, now is {}.".format(
                            old_preferredname, preferredname))
                if old_fullname != fullname:
                    print("    Full name was {}, now is {}.".format(
                            old_fullname, fullname))
                print("    Keeping the old names. You may want to change this.")
                preferredname = old_preferredname
                fullname = old_fullname
            tags += " " + classid
        else:
            tags = classid
        ankifile.write(";".join((
            studentid, 
            '<img src="UCLA_Student_{}.jpg">'.format(studentid), 
            preferredname, 
            fullname, 
            tags)) + "\n")
        if not args.textfile_only:
            downloads.append(studentid)

# Now download all the photos for the students specified in list "downloads". 
while downloads:
    errors = []
    for studentid in downloads:
        url = ("https://be.my.ucla.edu/fileRelay.aspx?"
            "type=R&uid={}&term={}&ci={}").format(studentid.replace("-", ""), 
            term, args.classindex)
        print("Downloading photo for student with ID {}".format(studentid))
        filename = "UCLA_Student_{}.jpg".format(studentid)
        pathname = os.path.join(ankimediadir, filename)
        if os.path.exists(pathname):
            newpathname = pathname[:-4] + ".new.jpg"
        else:
            newpathname = pathname
        try:
            subprocess.check_call(["wget", 
                "--load-cookies={}".format(args.cookiespath), 
                "-O", newpathname, url], stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL)
        except:
            print("    An error occurred with the previous download.")
            errors.append(studentid)
            continue
        if newpathname != pathname:
            if filecmp.cmp(newpathname, pathname):
                # The new one is the same as the old one. 
                os.remove(newpathname)
            else:
                # The new one is different! Use the new one, but keep the old. 
                oldpathname = pathname[:-4] + ".old.jpg"
                os.rename(pathname, oldpathname)
                os.rename(newpathname, pathname)
    print("{} photos downloaded successfully, {} errors.".format(
        len(downloads) - len(errors), len(errors)))
    downloads = errors
    if errors:
        print("Shall we retry the errors? [y/n] ")
        answer = sys.stdin.readline()
        if answer.lower()[0] != "y":
            break


