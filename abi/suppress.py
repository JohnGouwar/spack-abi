from spack.cmd.common import arguments
from spack.cmd import parse_specs, require_active_env
from spack.cmd.uninstall import find_matching_specs
#########
from argparse import ArgumentParser, REMAINDER
from pathlib import Path
from typing import List
#########
from spack.extensions.abi.common import AbiSubcommand, libs_for_spec, headers_for_spec
from spack.extensions.abi.abixml import ABI
from spack.extensions.abi.parse_headers import parse_header

try: # LSP can identify symbols
    from abi.abixml import ABI
    from abi.common import AbiSubcommand, libs_for_spec, headers_for_spec
    from abi.parse_headers import parse_header
except:
    pass

def suppression_for_binaries_from_header(binaries: List[Path], header: Path) -> str:
    abi, _ = ABI.from_binaries(binaries)
    header_types, header_functions, header_vars = parse_header(header)
    header_type_symbols = [ht.symbol for ht in header_types]
    header_function_symbols = [hf.symbol for hf in header_functions]
    private_types = [cd for cd in abi.class_decls if cd.name not in header_type_symbols]
    private_types += [td for td in abi.typedef_decls if td.name not in header_type_symbols]
    private_funcs = [fd for fd in abi.fun_decls if fd.name not in header_function_symbols]
    type_suppressions = [t.to_suppression(abi.path) for t in private_types]
    func_suppressions = [f.to_suppression(abi.path) for f in private_funcs]
    return "\n".join(type_suppressions + func_suppressions)


class SuppressCmd(AbiSubcommand):
    @classmethod
    def setup_subparser(cls, subparser: ArgumentParser):
        header_group = subparser.add_mutually_exclusive_group(required=True)
        subparser.add_argument(
            "--output-file",
            type=str,
            help="File to output libabigail supression information"
        )
        header_group.add_argument(
            "--header-name",
            type=str,
            help="Name of header used for public interface (path is resolved by spec)"
        )
        header_group.add_argument(
            "--header-path",
            type=str,
            help="The path to the header file used for public interface"
        )
        subparser.add_argument(
            "target",
            type=str,
            help="spec or shared object file to generate suppressions for",
            nargs=REMAINDER
        )


    @classmethod
    def cmd(cls, args):
        if args.target.ends_with(".so"):
            binaries = [Path(args.target)]
            assert args.header_path is not None, "Explicit binary requires explicit path to header"
            header = Path(args.header_path)
        else:
            env = require_active_env("abi suppress")
            installed_spec = find_matching_specs(env=env, specs=parse_specs(args.spec))[0]
            binaries = libs_for_spec(installed_spec)
            assert args.header_name is not None, "Explicit spec requires name of header file"
            header = [
                Path(h) for h in headers_for_spec(installed_spec)
                if Path(h).name == args.header_name
            ][0]
        suppression_text = suppression_for_binaries_from_header(binaries, header)
        if args.output_file:
            with open(args.output_file, "w") as f:
                f.write(suppression_text)
        else:
            print(suppression_text)
    

    @classmethod
    def description(cls) -> str:
        lines = [
            "Generate ABI suppression file for a particular spec or binary"
        ]
        return "\n".join(lines)
