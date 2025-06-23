from argparse import REMAINDER, ArgumentParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from warnings import showwarning
########
from spack.cmd import require_active_env, parse_specs
from spack.spec import Spec
########
from typing import Optional, List
from spack.extensions.abi.common import (
    AbiSubcommand,
    libs_for_spec,
    headers_for_spec,
    find_matching_specs
)
from spack.extensions.abi.abigail import abidiff, print_cmd, DiffExitCode
from spack.extensions.abi.suppress import suppression_for_binaries_from_header

try: # LSP can identify symbols
    from abi.common import AbiSubcommand, libs_for_spec, headers_for_spec, find_matching_specs
    from abi.suppress import suppression_for_binaries_from_header
    from abi.abigail import abidiff, print_cmd, DiffExitCode
except:
    pass

def diff_specs(
        spec1: Spec,
        spec2: Spec,
        header1: Optional[str] = None,
        suppr1: Optional[str] = None,
        header2: Optional[str] = None,
        suppr2: Optional[str] = None,
        show_cmd: bool = False,
        extra_args: List[str] = [],
):
    spec1_libs = libs_for_spec(spec1)
    spec2_libs = libs_for_spec(spec2)
    if header1:
        spec1_header = [h for h in headers_for_spec(spec1) if h.name == header1][0]
        spec1_suppression = suppression_for_binaries_from_header(spec1_libs, spec1_header)
    elif suppr1:
        with open(suppr1, "r") as f:
            spec1_suppression = f.read()
    else:
        spec1_suppression = ""
    if header2:
        spec2_header = [h for h in headers_for_spec(spec2) if h.name == header2][0]
        spec2_suppression = suppression_for_binaries_from_header(spec2_libs, spec2_header)
    elif suppr2:
        with open(suppr2, "r") as f:
            spec2_suppression = f.read()
    else:
        spec2_suppression = ""
    suppression_txt = spec1_suppression + spec2_suppression
    with NamedTemporaryFile(delete_on_close=False) as tf:
        if len(suppression_txt) != 0:
            tf.write(suppression_txt.encode("utf8"))
            tf.close()
            suppression_file = Path(tf.name)
        else:
            suppression_file = None
        result, args = abidiff(
            spec1_libs,
            spec2_libs,
            suppression_file=suppression_file,
            show_cmd=show_cmd,
            extra_args=extra_args
        )
        if result.returncode & DiffExitCode.USAGE_ERROR == 1:
            print("There was an error in running `abidiff`, below is the underlying command:")
            print_cmd(args)
            print(f"STDERR: {result.stderr}")
        else:
            print(result.stdout)
            print(result.stderr)
    

class DiffCmd(AbiSubcommand):
    @classmethod
    def setup_subparser(cls, subparser: ArgumentParser):
        subparser.add_argument(
            "--extra-args",
            type=str,
            help="Extra arguments which are passed through to `abidiff`, " 
            "enclose in quotes for multiple args"
        )
        subparser.add_argument(
            "--show-cmd",
            action="store_true",
            help="Show the underlying `abidiff` command that is executed"
        )
        spec1_group = subparser.add_mutually_exclusive_group()
        spec1_group.add_argument(
            "--header1",
            type=str,
            help="The name of the header file associated with the library for the first spec"
        )
        spec1_group.add_argument(
            "--suppr1",
            type=str,
            help="Path to handwritten suppressions files for spec1 "
        )
        spec2_group = subparser.add_mutually_exclusive_group()
        spec2_group.add_argument(
            "--header2",
            type=str,
            help="The name of the header file associate with the library for the second spec"
        )
        spec2_group.add_argument(
            "--suppr2",
            type=str,
            help="Path to handwritten suppressions files for spec2"
        )
        subparser.add_argument(
            "installed_specs",
            nargs=REMAINDER,
            help="Two installed specs in activated environment"
        )

    @classmethod
    def cmd(cls, args):
        specs = find_matching_specs(env=None, specs=parse_specs(args.installed_specs))
        assert (len(specs) == 2), "Cannot compare ABIs for more than 2 specs"
        spec1, spec2 = specs
        if args.extra_args:
            extra_args = args.extra_args.split()
        else:
            extra_args = []
        diff_specs(
            spec1,
            spec2,
            args.header1,
            args.suppr1,
            args.header2,
            args.suppr2,
            show_cmd=args.show_cmd,
            extra_args=extra_args
        )

    @classmethod
    def description(cls) -> str:
        lines = [
            "Run `abidiff` on two different specs"
        ]
        return "\n".join(lines)
