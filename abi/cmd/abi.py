import spack.cmd
#############
from argparse import ArgumentParser
from typing import List, Tuple
#############
from spack.extensions.abi.common import AbiSubcommand
from spack.extensions.abi.diff import DiffCmd
from spack.extensions.abi.suppress import SuppressCmd
from spack.extensions.abi.libs import LibsCmd
from spack.extensions.abi.abixml import XmlCmd
try:
    from abi.common import AbiSubcommand
    from abi.diff import DiffCmd
    from abi.suppress import SuppressCmd
    from abi.libs import LibsCmd
    from abi.abixml import XmlCmd
except:
    pass

description = "Analyze ABI artifacts in concrete Spack environments"
section = "spack-abi"
level = "long"

CMDS : List[Tuple[str, AbiSubcommand]]
CMDS = [
    ("diff", DiffCmd()),
    ("suppress", SuppressCmd()),
    ("libs", LibsCmd()),
    ("xml", XmlCmd()),
]
subcmd_funcs = {}

def setup_parser(parser: ArgumentParser):
    subparser = parser.add_subparsers(metavar="SUBCOMMAND", dest="abi_command")
    for (cmd_str, cmd_obj) in CMDS:
        subcmd_funcs[cmd_str] = cmd_obj.cmd
        subcmd_parser = subparser.add_parser(
            cmd_str,
            description=cmd_obj.description(),
            help=spack.cmd.first_line(cmd_obj.description())
        )
        cmd_obj.setup_subparser(subcmd_parser)
        
def abi(parser, args):
    subcommand = subcmd_funcs[args.abi_command]
    subcommand(args)
