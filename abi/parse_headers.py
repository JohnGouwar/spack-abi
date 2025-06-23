from pathlib import Path
from subprocess import run, PIPE
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Tuple, Generator
from tree_sitter import Language, Parser, Node
import tree_sitter_c as tsc
    
def run_preproc(header_file: Path) -> str:
    result = run(["gcc", "-E", str(header_file)], stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"GCC preprocessor failed on {str(header_file)} with stderr:\n{result.stderr}"
        )
    return result.stdout

class PreprocessorFlag(Enum):
    NEW_FILE = 1
    RETURNING_FILE = 2
    SYSTEM_FILE = 3
    EXTERN_TEXT = 4

class SymbolType(Enum):
    TYPEDEF = auto()
    FUNDEF = auto()
    PTRDEF = auto()
    EXTERNDEF = auto()
    STRUCTDEF = auto()
    ENUMDEF = auto()

@dataclass
class Symbol:
    stype : SymbolType
    symbol : str

    
def _parse_type_definition(node: Node):
    declarator = node.child_by_field_name("declarator")
    assert declarator is not None
    if declarator.type == "function_declarator":
        child_declarator = declarator.child_by_field_name("declarator")
        assert child_declarator is not None
        assert child_declarator.type == 'parenthesized_declarator'
        return Symbol(
            stype = SymbolType.TYPEDEF,
            symbol = child_declarator.text.decode("utf8")[1:-1]
        )
    elif declarator.type == "type_identifier":
        return Symbol(
            stype=SymbolType.TYPEDEF,
            symbol = declarator.text.decode("utf8")
        )
    elif declarator.type == "pointer_declarator":
        return Symbol(
            stype = SymbolType.TYPEDEF,
            symbol = declarator.child_by_field_name("declarator").text.decode("utf8")
        )
    else:
        print(f"Unhandled declarator in _parse_type_definition: {declarator.type}")
    return


def _parse_declaration(node: Node):
    declarator = node.child_by_field_name("declarator")
    assert declarator is not None
    if declarator.type == "function_declarator":
        name_node = declarator.child_by_field_name("declarator") 
        assert name_node.type == "identifier", f"Got {name_node.type}"
        return Symbol(stype=SymbolType.FUNDEF, symbol=name_node.text.decode("utf8"))
    elif declarator.type == "pointer_declarator":
        name_node = declarator.child_by_field_name("declarator") 
        return Symbol(stype=SymbolType.PTRDEF, symbol=name_node.text.decode("utf8"))
    elif declarator.type == "identifier":
        return Symbol(
            stype=SymbolType.EXTERNDEF,
            symbol=declarator.text.decode("utf8")
        )
    elif declarator.type == "array_declarator":
        return Symbol(
            stype=SymbolType.EXTERNDEF,
            symbol=declarator.child_by_field_name("declarator").text.decode("utf8")
        )
    else:
        print(f"Unhandled declarator in _parse_declaration: {declarator.type}")
        return


def _parse_struct_specifier(node: Node):
    return Symbol(
        stype=SymbolType.STRUCTDEF,
        symbol=node.child_by_field_name("name").text.decode("utf8")
    )

def _parse_enum_specifier(node: Node):
    try:
        return Symbol(
            stype=SymbolType.ENUMDEF,
            symbol=node.child_by_field_name("name").text.decode("utf8")
        )
    except:
        return
        
    
@dataclass
class HeaderBlock:
    file: Path
    flags: List[PreprocessorFlag]
    text: str

    def parse(self, parser: Parser):
        cursor = parser.parse(self.text.encode("utf8")).root_node.walk()
        cursor.goto_first_child()
        parsed = []
        while(True):
            assert cursor.node is not None
            if cursor.node.type == "type_definition":
                parsed.append(_parse_type_definition(cursor.node))
            elif cursor.node.type == "declaration":
                parsed.append(_parse_declaration(cursor.node))
            elif cursor.node.type == "struct_specifier":
                parsed.append(_parse_struct_specifier(cursor.node))
            elif cursor.node.type == "enum_specifier":
                parsed.append(_parse_enum_specifier(cursor.node))
            elif cursor.node.type == ";":
                pass
            else:
                print(f"Unhandled node: {cursor.node.type}")
            if not (cursor.goto_next_sibling()):
                break
        return [p for p in parsed if p is not None]
    
    
def _parse_file_line(line: str) -> Tuple[Path, List[PreprocessorFlag]]:
    _, _, filepath_quoted, *flags = line.split()
    parsed_flags = [PreprocessorFlag(int(f)) for f in flags]
    return (Path(filepath_quoted[1:-1]), parsed_flags)
    
def _parse_blocks(header_text: str) -> Generator[HeaderBlock]:
    '''
    (https://gcc.gnu.org/onlinedocs/cpp/Preprocessor-Output.html)
    Preprocessor output delimits which files things come from using the following form:
    # LINE_NUM "/path/to/file" 1 2 3 4
    The numbers at the end are optional and are flags with the following denotations
    1 - Start of a new file
    2 - Returning to file after having included another file
    3 - Text comes from a system header file
    4 - The following text should be treated as being wrapped in an extern "C" block
    '''
    lines = header_text.split("\n")
    curr_block_text = []
    curr_header = None
    for line in lines:
        if line.startswith("#"):
            if curr_header is None:
                curr_header = _parse_file_line(line)
            else:
                block = HeaderBlock(*curr_header, "\n".join(curr_block_text))
                yield block
                curr_header = _parse_file_line(line)
                curr_block_text = []
        else:
            if not (line.isspace() or len(line) == 0):
                curr_block_text.append(line)
    yield HeaderBlock(*curr_header, "\n".join(curr_block_text))

   
def parse_header(
        header_file: Path
) -> Tuple[List [Symbol], List [Symbol], List [Symbol]]:
    type_symbols = []
    var_symbols = []
    func_symbols = []
    def _separate_symbols(syms):
        for sym in syms:
            match sym.stype:
                case SymbolType.FUNDEF:
                    func_symbols.append(sym)
                case SymbolType.EXTERNDEF:
                    var_symbols.append(sym)
                case _:
                    type_symbols.append(sym)
        
    header_text = run_preproc(header_file)
    blocks = [
        b for b in _parse_blocks(header_text)
        if len(b.text) > 0 and PreprocessorFlag.SYSTEM_FILE not in b.flags 
    ]
    C_LANGUAGE = Language(tsc.language())
    parser = Parser(C_LANGUAGE)
    for b in blocks:
        _separate_symbols(b.parse(parser))
    return type_symbols, func_symbols, var_symbols 
    
    
