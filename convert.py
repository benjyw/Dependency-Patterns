#!/usr/bin/env python3.11
import json
import os
import sys


_files = {}
_adhoc_tool = {}
_run_shell_command = {}


def files(**kwargs):
    _files.update(**kwargs)


def adhoc_tool(**kwargs):
    _adhoc_tool.update(**kwargs)


def run_shell_command(**kwargs):
    _run_shell_command.update(**kwargs)

globals={"files": files, "adhoc_tool": adhoc_tool, "run_shell_command": run_shell_command}

n = 0

def convert(path: str):
    global n
    normpath = os.path.normpath(path)
    if os.path.isdir(path) and normpath != "pants-plugins/BUILD":
        for root, _, files in os.walk(path):
            for file in files:
                full_path = os.path.join(root, file)
                convert(full_path)
    elif os.path.isfile(path):
        output_dict = {}
        if os.path.basename(path) == "BUILD" and normpath != "scaling/geomorphy/BUILD":
            with open(path, "r") as fp:
                content = fp.read()
            exec(content, globals)
            if normpath == "scaling/BUILD":
                output_dict = {
                    "dependencies": sorted(set(d.removeprefix("//").removesuffix(":output") for d in _run_shell_command["execution_dependencies"])),
                }
            else:
                output_dict = {
                    "sources": _files["sources"],
                    "dependencies": sorted(d.removesuffix(":output") for d in _adhoc_tool["execution_dependencies"] if d not in  {":output_sources", "geomorphy:run_build_script"}),
                    "output_file": _adhoc_tool["output_files"][0]
                }
        if output_dict:
            output_path = os.path.join(os.path.dirname(path), "build.json")
            with open(output_path, "w") as fp:
                json.dump(output_dict, fp, indent=2)
            os.unlink(path)
            n += 1
            if n % 100 == 0:
                print(f"Converted {n} BUILD files")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        convert(arg)
        print(f"Converted {n} BUILD files.")
        print("Done!")

