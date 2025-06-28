try:
    from spack.extensions.abi.abigail import DiffExitCode, print_cmd
    from spack.extensions.abi.common import AbiSubcommand
    from spack.extensions.abi.diff import diff_specs
except:
    from abi.abigail import DiffExitCode, print_cmd
    from abi.common import AbiSubcommand
    from abi.diff import diff_specs
from argparse import ArgumentParser
from pathlib import Path
from enum import Enum, auto


from spack.environment import Environment

import sys
from typing import TypeVar, List, Tuple
T = TypeVar('T')

class AbiDiffType(Enum):
    NONE = auto()
    HARMLESS = auto()
    HARMFUL = auto()
    ERROR = auto()

def return_code_to_diff_type(rc: int) -> AbiDiffType:
    if rc == 0:
        return AbiDiffType.NONE
    elif rc & DiffExitCode.ABI_CHANGE == DiffExitCode.ABI_CHANGE:
        if rc & DiffExitCode.INCOMPATIBLE_CHANGE == 0:
            return AbiDiffType.HARMLESS
        else:
            return AbiDiffType.HARMFUL
    else: # There was a usage error
        return AbiDiffType.ERROR

    
def cross_product_self(lst: List[T]) -> List[Tuple[T, T]]:
    """
    Computes the cross product of a list with itself, skipping elements
    which are at the same index (so as not to rely on == for equality)
    """
    return [
        (elt1, elt2)
        for i, elt1 in enumerate(lst)
        for j, elt2 in enumerate(lst)
        if i != j
    ]

class DiffProductCmd(AbiSubcommand):
    @classmethod
    def setup_subparser(cls, subparser: ArgumentParser):
        subparser.add_argument(
            "env",
            type=str,
            help="A directory containing a valid spack.yaml file"
        )
        subparser.add_argument(
            "--output-format",
            choices=["raw", "summary", "can_splice"],
            default="raw",
            help="(raw) abidiff output, (summary) of abidiff out, valid (can_splice) facts"
        )
        subparser.add_argument(
            "--output-file",
            type=str,
            help="File for generated output, defaults to stdout"
        )

    @classmethod
    def description(cls) -> str:
        lines = [
            "Run `abidiff` over the cross-product of root specs in a provided environment.",
            "Note that this environment need not be active."
        ]
        return "\n".join(lines)
    
    @classmethod
    def cmd(cls, args):
        env = Environment(Path(args.env).absolute())
        with env.manifest.use_config():
            env.concretize()
            env.install_all()
            env.write()
        comparisons = cross_product_self(list(env.concretized_specs()))
        if args.output_file:
            outfile = open(args.output_file, "w")
        else:
            outfile = sys.stdout
        for (u1, c1), (u2, c2) in comparisons:
            result, abidiff_args = diff_specs(c1, c2)
            diff_type = return_code_to_diff_type(result.returncode)
            if args.output_format == "can_splice":
                match diff_type:
                    case AbiDiffType.NONE | AbiDiffType.HARMLESS:
                        print(f"can_splice(\"{u1}\", when=\"{u2}\") #{diff_type}", file=outfile)
                    case AbiDiffType.HARMFUL:
                        print(f"# No splice {u1} and {u2}")
                        continue
                    case AbiDiffType.ERROR:
                        print(f"abidiff reported a usage error when comparing {u1} and {u2}")
                        print_cmd(abidiff_args)
            elif args.output_format == "summary":
                pass
            else: # raw
                print(f"Comparing {u1},{c1} to {u2},{c2}", file=outfile)
                print(result.stdout, file=outfile)
                print(result.stderr)
        if outfile != sys.stdout:
            outfile.close()
