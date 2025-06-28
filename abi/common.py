from abc import ABC, abstractmethod
from spack.error import SpackError
from spack.spec import Spec
from spack.enums import InstallRecordStatus
from spack.cmd import display_specs
import sys
import spack.environment as ev
import spack.store
from typing import List, Self, Optional
from pathlib import Path
from argparse import ArgumentParser

class AbiSubcommand(ABC):
    @classmethod
    @abstractmethod
    def setup_subparser(cls, subparser: ArgumentParser): ...

    @classmethod
    @abstractmethod
    def cmd(cls, args): ...

    @classmethod
    @abstractmethod
    def description(cls) -> str: ...

    def __new__(cls) -> Self:
        return super().__new__(cls)


def _spec_to_build_interface(spec: Spec):
    if not spec.installed:
        raise SpackError(
            f"Spec {spec} must be installed to analyze ABI. "
            "Try `spack install` "
        )
    return spec[spec.name]

def libs_for_spec(spec: Spec) -> List[Path]:
    spec_bi = _spec_to_build_interface(spec)
    return [Path(l) for l in spec_bi.libs]

def headers_for_spec(spec: Spec) -> List[Path]:
    spec_bi = _spec_to_build_interface(spec)
    return [Path(l) for l in spec_bi.headers]

def regex_for_filename(file: Path):
    name, ext = file.name.split('.')
    return f"{name}\\\\.{ext}"

def find_matching_specs(
        env: Optional[ev.Environment],
        specs: List[Spec]
) -> List[Spec]:
    hashes = env.all_hashes() if env else None
    found_specs = []
    for spec in specs:
        matching = spack.store.STORE.db.query_local(
            spec,
            hashes=hashes,
            installed=(InstallRecordStatus.INSTALLED | InstallRecordStatus.DEPRECATED),
            origin=None
        )
        if len(matching) > 1:
            display_args = {
                "output": sys.stderr,
                "long": True,
                "show_flags": False,
                "variants": False,
                "indent": 4
            }
            print(f"{spec} matches multiple packages", file=sys.stderr)
            display_specs(matching, **display_args)
            print(f"Try specifying the desired spec by its hash", file=sys.stderr)
            exit(1)
        if len(matching) == 0:
            loc = env.name if env else "installed packages"
            print(f"Failed to find {spec} in {loc}", file=sys.stderr)
            exit(1)
        found_specs.append(matching[0])
    return found_specs

            
