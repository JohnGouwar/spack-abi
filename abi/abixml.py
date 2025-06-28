from argparse import ArgumentParser
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET
from subprocess import run, PIPE
from shutil import which
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Self, List, Union, Tuple, Optional
from pprint import pformat
from spack.cmd import parse_specs, require_active_env
from spack.cmd.common import arguments
try:
    from spack.extensions.abi.abigail import abidw
    from spack.extensions.abi.common import AbiSubcommand, find_matching_specs, libs_for_spec
except:
    from abi.common import AbiSubcommand, find_matching_specs, libs_for_spec
    from abi.abigail import abidw

def _get_or_fail(xelt: ET.Element, attr: str) -> str:
    output = xelt.get(attr)
    if output is None:
        raise AttributeError(attr, xelt.keys())
    return output

def _find_or_fail(xelt: ET.Element, node: str) -> ET.Element:
    output = xelt.find(node)
    if output is None:
        raise AttributeError(node, xelt)
    return output

class ABIXML(ABC):
    '''
    The root visitor for all ABIXML elts. `from_xmlelt` is the visiting function
    '''
    @staticmethod
    @abstractmethod 
    def abixml_tag() -> str: ...
    
    @classmethod
    @abstractmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self : ...

    @classmethod
    def as_children(cls, parent: Optional[ET.Element]) -> List[Self]:
        if parent:
            return [cls.from_xmlelt(x) for x in parent.findall(cls.abixml_tag())]
        else:
            return []

    def to_supression(self, file: Path) -> str: ...

@dataclass
class Symbol(ABIXML):
    name: str
    size: int
    typ: str
    binding: str
    visibility: str
    defined: bool

    @staticmethod
    def abixml_tag() -> str:
        return "elf-symbol"
        
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        return cls(
            name=_get_or_fail(xelt, "name"),
            size=int(xelt.get('size', 0)),
            typ=_get_or_fail(xelt, "type"),
            binding=_get_or_fail(xelt, "binding"),
            visibility=_get_or_fail(xelt, "visibility"),
            defined=_get_or_fail(xelt, "is-defined") == 'yes'
        )

@dataclass
class VarDecl(ABIXML):
    name: str
    type_id: str
    visibility: str
    filepath: Optional[Path]

    @staticmethod
    def abixml_tag() -> str:
        return "var-decl"
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        if xelt.get('filepath') is not None:
            filepath = Path(xelt.get('filepath'))
        else:
            filepath = None
        return cls(
            name=_get_or_fail(xelt, "name"),
            type_id=_get_or_fail(xelt, "type-id"),
            visibility=_get_or_fail(xelt, "visibility"),
            filepath=filepath
        )
    
@dataclass
class TypeDecl(ABIXML):
    name: str
    size: Optional[int]
    hash: Optional[str]
    id: str
    
    @staticmethod
    def abixml_tag() -> str:
        return "type-decl"
        
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        if xelt.get("size-in-bits") is not None:
            size = int(xelt.get("size-in-bits"))
        else:
            size = None
        return cls(
            name=_get_or_fail(xelt, "name"),
            size=size,
            hash=xelt.get("hash"),
            id=_get_or_fail(xelt, "id")
        )
    
@dataclass    
class Parameter(ABIXML):
    type_id: Optional[str]
    name: Optional[str]
    is_variadic: bool
        
    @staticmethod
    def abixml_tag() -> str:
        return "parameter"
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        return cls(
            type_id=xelt.get("type-id"),
            name=xelt.get("name"),
            is_variadic=xelt.get("is_variadic") == "yes"
        )

@dataclass    
class FunctionDecl(ABIXML):
    name: str
    mangled_name: Optional[str]
    filepath: Optional[Path]
    parameters: List[Parameter]
    return_type_id: str
    

    @staticmethod
    def abixml_tag() -> str:
        return "function-decl"
    
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        if xelt.get('filepath') is not None:
            filepath = Path(xelt.get('filepath'))
        else:
            filepath = None
        return cls(
            name=_get_or_fail(xelt, "name"),
            mangled_name=xelt.get("mangled-name"),
            filepath=filepath,
            parameters=Parameter.as_children(xelt),
            return_type_id=_get_or_fail(_find_or_fail(xelt, "return"), "type-id")
        )
    def to_suppression(self, file: Path) -> str:
        output_lines = [
            "[suppress_function]",
            f"name = {self.name}",
            # f"file_name_regexp = {regex_for_filename(file)}"
        ]
        return "\n  ".join(output_lines)
    

@dataclass
class DataMember(ABIXML):
    access: str
    layout_offset: int
    decl : Union[FunctionDecl, VarDecl]

    @staticmethod
    def abixml_tag() -> str:
        return "data-member"
    
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        decl_xml = xelt.find(VarDecl.abixml_tag())
        if decl_xml is None: # if it is not VarDecl, it must be a function decl
            decl_xml = _find_or_fail(xelt, FunctionDecl.abixml_tag())
            decl = FunctionDecl.from_xmlelt(decl_xml)
        else:
            decl = VarDecl.from_xmlelt(decl_xml)
        return cls(
            access=_get_or_fail(xelt, "access"),
            layout_offset=int(_get_or_fail(xelt, "layout-offset-in-bits")),
            decl=decl
        )

@dataclass
class ClassDecl(ABIXML):
    name: str
    is_struct: bool
    visibility: str
    size: Optional[int] 
    filepath: Optional[Path]
    hash: Optional[str]
    id: str
    data_members: List[DataMember]
    
    @staticmethod
    def abixml_tag() -> str:
        return "class-decl"
    
    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        opt_size = xelt.get("size-in-bits")
        opt_path = xelt.get('filepath')
        if opt_size:
            size = int(opt_size)
        else:
            size = None
        if opt_path:
            filepath = Path(opt_path)
        else:
            filepath = None
        return cls(
            name = _get_or_fail(xelt, "name"),
            is_struct = _get_or_fail(xelt, "is-struct") == 'yes',
            visibility = _get_or_fail(xelt, "visibility"),
            size = size,
            filepath = filepath,
            hash = xelt.get("hash"),
            id = _get_or_fail(xelt, "id"),
            data_members = DataMember.as_children(xelt)
        )

    def to_suppression(self, file: Path) -> str:
        output_lines = [
            "[suppress_type]",
            f"name = {self.name}",
            # f"file_name_regexp = {regex_for_filename(file)}"
        ]
        return "\n  ".join(output_lines)

@dataclass
class TypedefDecl(ABIXML):
    name: str
    member_id: str
    type_id: str
    filepath: Path

    @staticmethod
    def abixml_tag() -> str:
        return "typedef-decl"

    @classmethod
    def from_xmlelt(cls, xelt: ET.Element) -> Self:
        return cls(
            name = _get_or_fail(xelt, "name"),
            member_id = _get_or_fail(xelt, "type-id"),
            type_id = _get_or_fail(xelt, "id"),
            filepath = Path(_get_or_fail(xelt, "filepath"))
        )

    def to_suppression(self, file: Path) -> str:
        output_lines = [
            "[suppress_type]",
            f"name = {self.name}",
            #f"file_name_regexp = {regex_for_filename(file)}"
        ]
        return "\n  ".join(output_lines)
        

@dataclass
class ABI:
    '''
    General structure of ABI-corpus
    '''
    path: Path
    fun_symbols : List[Symbol]
    var_symbols : List[Symbol]
    type_decls : List[TypeDecl]
    typedef_decls: List[TypedefDecl]
    class_decls : List[ClassDecl]
    fun_decls : List[FunctionDecl]
    var_decls : List[VarDecl]
            
    @classmethod
    def from_binaries(
            cls,
            bins: List[Path],
            suppression_file: Optional[Path] = None,
            show_cmd: bool = False,
            extra_args: List[str] = []
    ) -> Tuple[Self, str]:
        result = abidw(
            bin,
            suppression_file=suppression_file,
            show_cmd=show_cmd,
            extra_args=extra_args
        )
        if result.returncode != 0:
            raise RuntimeError(f"abidw failed with the following stderr:\n{result.stderr}")
        xml_str = result.stdout
        return (cls.from_xml(xml_str), xml_str)

    @classmethod
    def from_xml(cls, xml_str: str) -> Self:
        root = ET.fromstring(xml_str)
        path = Path(_get_or_fail(root, "path"))
        type_decls = []
        class_decls = []
        fun_decls = []
        typedef_decls = []
        var_decls = []
        fun_symbols = Symbol.as_children(_find_or_fail(root, 'elf-function-symbols'))
        var_symbols = Symbol.as_children(root.find('elf-variable-symbols'))
        for decls_root in root.findall("abi-instr"):
            type_decls.extend(TypeDecl.as_children(decls_root))
            class_decls.extend(ClassDecl.as_children(decls_root))
            fun_decls += FunctionDecl.as_children(decls_root)
            typedef_decls.extend(TypedefDecl.as_children(decls_root))
            var_decls.extend(VarDecl.as_children(decls_root))
        return cls(
            path = path,
            fun_symbols = fun_symbols,
            var_symbols = var_symbols,
            class_decls = class_decls,
            fun_decls = fun_decls,
            type_decls = type_decls,
            typedef_decls = typedef_decls,
            var_decls = var_decls
        )
    def type_and_function_names(self) -> Tuple[List[str], List[str]]:
        type_names = [cd.name for cd in self.class_decls] + [td.name for td in self.typedef_decls]
        func_names = [fd.name for fd in self.fun_decls]
        return type_names, func_names

class XmlCmd(AbiSubcommand):
    @classmethod
    def setup_subparser(cls, subparser: ArgumentParser):
        arguments.add_common_arguments(subparser, ["installed_spec"])
        subparser.add_argument(
            "--extra-args",
            type=str,
            help="Extra arguments which are passed through to `abidw`, " 
            "enclose in quotes with = for multiple args"
        )
        subparser.add_argument(
            "--output-file",
            type=str,
            help="File for storing output (default stdout)"
        )
        subparser.add_argument(
            "--output-format",
            choices=["xml", "names", "ir"],
            default="xml",
            help="ABI(xml) text, A newline separated list of all parsed (names), "
            "The (ir) for debugging"
        )
        subparser.add_argument(
            "--suppression-file",
            type=str,
            help="A path to a file containing a libabigail suppression specification"
        )

    @classmethod
    def cmd(cls, args):
        specs = find_matching_specs(env=None, specs=parse_specs(args.spec))
        assert (len(specs) == 1), "Cannot analyze ABI for more than one spec at a time"
        spec = specs[0]
        spec_libs = libs_for_spec(spec)
        abi_obj, xml_str = ABI.from_binaries(
            spec_libs,
            suppression_file=args.suppression_file,
            show_cmd=args.show_cmd,
            extra_args=args.extra_args
        ) 
        if args.output_format == "xml":
            output_text = xml_str
        elif args.output_format == "names":
            type_names, func_names = abi_obj.type_and_function_names()
            output_text = "\n".join(type_names + func_names)
        else:  
            output_text = pformat(abi_obj)
        if args.output_file:
            with open(args.output_file, "w") as f:
                f.write(output_text)
        else:
            print(output_text)

    @classmethod
    def description(cls) -> str:
        lines = [
            "A wrapper over abidw for generating .abixml files for specs",
        ]
        return "\n".join(lines)

    
