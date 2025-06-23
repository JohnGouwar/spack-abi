from enum import IntFlag
from subprocess import run, PIPE
from shutil import which
from typing import List, Optional, Tuple
from pathlib import Path
from os import PathLike


class DiffExitCode(IntFlag):
    OK = 0
    DIFF_ERROR = 1
    USAGE_ERROR = 2
    ABI_CHANGE = 4
    INCOMPATIBLE_CHANGE = 8

def print_cmd(args):
    cmd = args[0]
    print("---------------")
    print(cmd)
    for arg in args[1:]:
        print(f"  {arg}")
    print("---------------")

def _which_ensure(cmd: str) -> str:
    cmd_path = which(cmd)
    if cmd_path is None:
        raise RuntimeError(f"Unable to find `{cmd}` executable in PATH")
    return cmd_path

def _split_bins_and_dirs(raw_bins: List[Path]) -> Tuple[str, List[str]]:
    bin_files = []
    bin_dirs = set()
    if len(raw_bins) > 0:
        for p in raw_bins:
            bin_files.append(p.name)
            bin_dirs.add(str(p.parent))
    bin_files_arg = ",".join(bin_files)    
    return (bin_files_arg, list(bin_dirs))
    
        
    
def abidiff(
        bins1 : List[Path],
        bins2: List[Path],
        suppression_file: Optional[Path] = None,
        show_cmd: bool = False,
        extra_args: List[str] = [] # makes it easy to add extra while prototyping
        
):
    cmd = _which_ensure("abidiff")
    bin1 = bins1[0]
    bin2 = bins2[0]
    added_bins_arg1, added_dirs1 = _split_bins_and_dirs(bins1[1:])
    added_bins_arg2, added_dirs2 = _split_bins_and_dirs(bins2[1:])
    args = [cmd] + extra_args
    if suppression_file:
        args += ["--suppr", str(suppression_file.absolute())]
    if len(added_bins_arg1) > 0:
        args.append(f"--add-binaries1={added_bins_arg1}")
    if len(added_bins_arg2) > 0:
        args.append(f"--add-binaries2={added_bins_arg2}")
    for d in added_dirs1:
        args.append("--added-binaries-dir1")
        args.append(d)
    for d in added_dirs2:
        args.append("--added-binaries-dir2")
        args.append(d)
    args.append(str(bin1.absolute()))
    args.append(str(bin2.absolute()))
    if show_cmd:
        print_cmd(args)
    return run(args, stdout=PIPE, stderr=PIPE, text=True), args
    
    

def abidw(
        bins: List[Path],
        suppression_file: Optional[Path] = None,
        show_cmd: bool = False,
        extra_args : List[str] = [], 
):
    bin, *added_bins = bins
    added_bins_arg, added_dirs = _split_bins_and_dirs(added_bins)
    cmd = _which_ensure("abidw")
    args = [cmd] + extra_args
    if len(added_bins_arg) > 0:
        args.append(f"--add-binaries={added_bins_arg}")
    for d in added_dirs:
        args.append("--abd")
        args.append(d)
    if suppression_file:
        args += ["--suppressions", str(suppression_file.absolute())]
    args.append(str(bin))
    if show_cmd:
        print_cmd(args)
    return run(args, stdout=PIPE, stderr=PIPE, text=True)
