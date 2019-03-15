"""
   Originally created by Fernando Balandran
   Updated and maintained by Fernando Balandran (fernando@kodaman.tech)

   Copyright 2018 Fernando Balandran

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

from pylogix import PLC
from ping3 import ping
import configparser
import sys
import time
from pathlib import Path
from progress.bar import Bar
import datetime
import re

# variables are read from Settings.ini
main_controller_ip = ''
dp_save_file_path = ''
tags_list = []
tag_types = ["BOOL", "BIT", "REAL", "DINT", "SINT"] # Might want to add this to settings?
files = []
file_extension = ''
comm = PLC()
CODE_VERSION = "1.0.6"
log = open("log.txt", "a+")
now = datetime.datetime.now()
checkErrorLog = False


def get_data_preserve(file):
    global tags_list
    del tags_list[:]

    with open(dp_save_file_path + file + "." + file_extension) as f:
        all_lines = f.readlines()

    # need to check empty lines, and more than one tag in one line here
    all_lines = remove_empty(all_lines)
    all_lines = check_multiple(all_lines, file)

    print("Config file: {}".format(file))
    bar = Bar('Saving', max=len(all_lines))

    for index in range(len(all_lines)):
        process_line_save(all_lines[index] + "\n", index + 1, file)
        bar.next()
    bar.finish()
    print("\n")

    with open(dp_save_file_path + file + "_Save." + file_extension, "w") as dp_save_file:
        dp_save_file.writelines(tags_list)


def load_verify_data_preserve(file, verify_only=False):

    with open(dp_save_file_path + file + "_Save." + file_extension) as f:
        all_lines = f.readlines()

    all_lines = remove_empty(all_lines)
    print("Config file: {}".format(file))
    bar = Bar('Loading', max=len(all_lines))
    bar2 = Bar('Verifying', max=len(all_lines))

    # do not load if only doing verification
    if not verify_only:
        for index in range(len(all_lines)):
            process_line_load(all_lines[index], index + 1, file)
            bar.next()
        bar.finish()

    # Verify online data afterwards
    passed = 0
    failed = 0
    for index in range(len(all_lines)):
        tag_verification = process_line_verification(all_lines[index], index + 1, file)
        bar2.next()
        if tag_verification:
            passed += 1
        else:
            failed += 1
    bar2.finish()

    print("\rVerification results: %d+ %d-\n" % (passed, failed))


def read_tag(tag):
    return comm.Read(tag)


def remove_empty(lines):
    clean_list = []
    # first remove return line
    clean_list = [line.rstrip('\n') for line in lines]
    # remove empty items
    clean_list = list(filter(None, clean_list))
    return clean_list


def check_multiple(lines, file_name):
    clean_list = []
    line_list = []
    current_tag_type = ""
    # if the tag type is in the same line twice
    # search if there are more than two
    for index in range(len(lines)):
        if lines[index].count("|") > 2:
            log.write("%s Save Info: %s line %s Multiple tags in one line\n" % (now.strftime("%c"), file_name, index+1))
            # process line here, and split into more items
            clean_list.extend(split_tag_lines(lines[index]))
        else:
            clean_list.append(lines[index])

    return clean_list


def split_tag_lines(line):
    how_many_tags = 0
    split_tags = []
    clean_list = []
    current_tag_type = ""
    # count how many tags for each two || is one tag
    how_many_tags = line.count("|") // 2

    split_tags = re.split(r'(DINT|BOOL|SINT|BIT|REAL)', line)

    # append to list
    for i in range(0, how_many_tags*2, 2):
        clean_list.append(split_tags[i] + split_tags[i+1])

    return clean_list


def process_line_save(line, line_number, file_name):
    global tags_list
    global checkErrorLog

    # split line
    plc_tag, dp_value, tag_type = line.split("|")

    # read online value, try, except in case tag doesn't exists
    try:
        dp_value = read_tag(plc_tag)
        put_string = plc_tag + "|" + str(dp_value) + "|" + str(tag_type)

        # append to list
        tags_list.append(put_string)

    except ValueError as e:
        log.write("%s Save Error: %s line %s %s\n" % (now.strftime("%c"), file_name, line_number, e))
        checkErrorLog = True


def process_line_load(line, line_number, file_name):
    global checkErrorLog
    # split line
    plc_tag, dp_value, tag_type = line.split("|")
    tag_type = tag_type.rstrip("\n")

    # write value to plc
    # bool are handled special
    # it expects True or False, 1 or 0, not a string
    if tag_type == "BOOL" or tag_type == "BIT":
        if dp_value == "True":
            dp_value = True
        if dp_value == "False":
            dp_value = False

    try:
        comm.Write(plc_tag, dp_value)
    except ValueError as e:
        log.write("%s Load Error: %s line %s %s\n" % (now.strftime("%c"), file_name, line_number, e))
        checkErrorLog = True


def process_line_verification(line, line_number, file_name):
    global checkErrorLog
    # split line
    plc_tag, dp_value, tag_type = line.split("|")

    try:
        str_tag = str(read_tag(plc_tag))
    except ValueError as e:
        log.write("%s Verify Error: %s line %s %s\n" % (now.strftime("%c"), file_name, line_number, e))
        str_tag = "None"
        checkErrorLog = True

    # if it matches return true
    if str_tag == dp_value:
        return True
    else:
        return False


def yes_or_no(question):
    while "the answer is invalid":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[0] == 'y':
            return True
        if reply[0] == 'n':
            return False


if __name__ == '__main__':

    config = configparser.ConfigParser()
    config.read('Settings.ini')
    main_controller_ip = config['Settings']['PLC_IP']
    comm.IPAddress = main_controller_ip
    comm.ProcessorSlot = int(config['Settings']['PLC_SLOT'])
    dp_save_file_path = config['Settings']['Save_Path']
    file_extension = config['Settings']['Files_Extension']

    # load file names from ini
    for key in config['Files_Path']:
        files.append(config['Files_Path'][key])

    # prompt user if to save or load
    print("Data Preserve Utility " + CODE_VERSION)
    answer = input('Options [save, load, verify]\n')

    # ping doesn't work on softlogix so uncomment when ready to ship
    if ping(main_controller_ip) is None:
        print("Check Settings.ini or ethernet connection!")
        sys.exit()

    if answer == "load":
        if yes_or_no("Are you sure?"):

            # ensure file names from ini have their save counterparts
            for config_file in files:
                temp_file = Path(dp_save_file_path + config_file + "_Save." + file_extension)
                if not temp_file.is_file():
                    print("Please save data preserve first!")
                    sys.exit()

            print("Loading data preserve...\n")

            for config_file in files:
                load_verify_data_preserve(config_file)

            if checkErrorLog:
                print("Check log.txt in root directory for errors!")

            input("Press Enter to exit...")
            log.close()
        else:
            print("Exiting...")
            log.close()
            sys.exit()

    if answer == "save":
        # ensure file names exist
        for config_file in files:
            temp_file = Path(dp_save_file_path + config_file + "." + file_extension)
            if not temp_file.is_file():
                print("Data preserve files not found!")
                sys.exit()

        print("Saving data preserve...\n")

        # save data for every file under Files_Path
        for config_file in files:
            get_data_preserve(config_file)

        if checkErrorLog:
            print("Check log.txt in root directory for errors!")

        input("Press Enter to exit...")
        log.close()

    if answer == "verify":
        # ensure file names from ini have their save counterparts
        for config_file in files:
            temp_file = Path(dp_save_file_path + config_file + "_Save." + file_extension)
            if not temp_file.is_file():
                print("Please save data preserve first!")
                sys.exit()

        print("Verifying data...\n")

        for config_file in files:
            load_verify_data_preserve(config_file, True)

        if checkErrorLog:
            print("Check log.txt in root directory for errors!")

        input("Press Enter to exit...")
        log.close()
