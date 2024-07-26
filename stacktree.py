#!/usr/bin/env python3
## Print stack tree by process name
## Ivan Markin 26/07/2024

from subprocess import Popen, PIPE, DEVNULL
import sys
import json
import time
import signal
import re
import os
import psutil
import getpass

from PrettyPrint import PrettyPrintTree

def is_threaded(pid):
    return len(os.listdir(f'/proc/{pid}/task')) > 1

def get_pids_by_name(process_name):
    username = getpass.getuser()
    user_proccesses = [process for process in psutil.process_iter() if process.username() == username]
    pids = []
    for proc in user_proccesses:
        if process_name in proc.name():
            pids += [proc.pid]
    return pids

running = True

def signal_handler(sig, frame):
    global running
    running = False
    print("Terminating.")

signal.signal(signal.SIGINT, signal_handler)


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def get_backtrace(pid):
    def preexec_function():
        os.setpgrp()
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    backtrace_cmd = "bt"
    if is_threaded(pid):
        backtrace_cmd = "thread apply all bt"
    gdb_cmdline = ['gdb', '--batch', '-ex', backtrace_cmd, '-ex', 'quit', f'/proc/{pid}/exe', f'{pid}']
    process = Popen(gdb_cmdline, stdout=PIPE, stderr=DEVNULL, preexec_fn=preexec_function)
    pstack_output = process.communicate()[0]
    process.wait()
    # pstack_output = subprocess.check_output(['pstack', pid])
    return pstack_output.decode("utf-8")

def parse_function_call(line):
    sp = line.split()
    fcall = {
        "depth": int(sp[0].removeprefix("#")),
        "function": sp[3],
        # "args": sp[4],
        "line": sp[-1],
    }
    if sp[2] != "in":
        return None
    return fcall


class Tree:
    def __init__(self, value):
        self.val = value
        self.children = []

    def add_child(self, child):
        self.children.append(child)
        return child

def thread_tree(thread, with_lines=False):
    tree = Tree(thread[0]["function"])
    child = tree
    for fcall in thread[1:]:
        text = fcall["function"]
        if with_lines:
            if len(fcall["line"]) > 40:
                break
            text = f'{fcall["function"]} ({fcall["line"]})'
        child = child.add_child(Tree(text))
    return tree


def tracetree(pid, include_pattern, with_lines=False, ):
    include_pattern = re.compile(include_pattern)

    bt = get_backtrace(pid)
    threads = {}

    lines = bt.splitlines()
    current_thread = None
    for line in lines:
        if line.__contains__(" from "):
            continue
        if line.__contains__("??"):
            continue
        if line.startswith("Thread"):
            thread_number = int(line.split()[1])
            current_thread = thread_number
        if line.startswith("#"):
            fcall = parse_function_call(line)
            if fcall is None:
                continue
            if not current_thread in threads:
                threads[current_thread] = []
            threads[current_thread].insert(0, {
                "function": fcall["function"],
                "line": fcall["line"],
            })


    process_tree = Tree(f"{bcolors.OKGREEN}PID {pid}{bcolors.ENDC}")
    for thread_key in threads.keys():
        thread = threads[thread_key]
        if not include_pattern.match(thread[0]["function"]):
                continue
        ttree = thread_tree(thread, with_lines=with_lines)
        process_tree.add_child(ttree)
    return process_tree

if __name__ == "__main__":
    process_name = sys.argv[1]
    with_lines = False

    include_pattern = "main|.*omp.*"
    tree = Tree(f"{bcolors.HEADER}{process_name}{bcolors.ENDC}")
    for pid in get_pids_by_name(process_name):
        pid_tree = tracetree(pid, with_lines=with_lines, include_pattern=include_pattern)
        tree.add_child(pid_tree)

    pt = PrettyPrintTree(lambda x: x.children, lambda x: x.val)
    print("\n\n\n")
    pt(tree)
    print("\n\n\n")