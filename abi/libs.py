from argparse import ArgumentParser
from spack.cmd import parse_specs, require_active_env 
from spack.cmd.common import arguments
from spack.cmd.uninstall import find_matching_specs
from spack.extensions.abi.common import AbiSubcommand, libs_for_spec, headers_for_spec
try:
    from .common import AbiSubcommand, libs_for_spec, headers_for_spec
except:
    pass

class LibsCmd(AbiSubcommand):
    @classmethod
    def setup_subparser(cls, subparser: ArgumentParser):
        arguments.add_common_arguments(subparser, ["installed_spec"])

    @classmethod
    def cmd(cls, args):
        env=require_active_env("abi libs")
        spec = find_matching_specs(env=env, specs=parse_specs(args.spec))[0]
        headers = headers_for_spec(spec)
        libs = libs_for_spec(spec)
        indent = " " * 2
        stars = "*" * 20
        print(f"***Headers for {spec}***")
        for h in headers:
            print(f"{indent}{h}")
        print(stars)
        print(f"***Libs for {spec}***")
        for l in libs:
            print(f"{indent}{l}")

    @classmethod
    def description(cls) -> str:
        lines = [
            "List the libs and headers considered for the given spec",
            "This is mostly useful for quickly debugging which binaries and headers are used"
        ]
        return "\n".join(lines)
