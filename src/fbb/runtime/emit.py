"""Runtime fonksiyonlarını Freya'nın çalıştıracağı tek parça Python snippet'ine çevirir.

- Sadece giriş kodunun gerçekten kullandığı fonksiyonlar (AST ile bulunan kapanış) eklenir.
- Spec sabitleri `RT` olarak JSON'dan yüklenir.
- Kaynakta iki süslü parantez yan yana olmaz: Freya `{{var}}` şablonlarını kodda da çözebilir (kit
  tools-and-code.md "Rules for snippets"). Bu kontrol ihlal olursa hata fırlatır.
- Giriş kodu try/except içine alınır; snippet hiçbir zaman hata fırlatmaz.
"""
from __future__ import annotations

import ast
import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
RUNTIME_FILES = ["dates.py", "normalize.py", "facts.py", "validate.py", "closing.py", "flow.py"]
HEADER = "import datetime\nimport json\nimport re\n"


class SnippetError(ValueError):
    pass


@lru_cache(maxsize=1)
def _definitions() -> dict[str, tuple[str, set[str]]]:
    """Ad → (kaynak, kullandığı adlar). Fonksiyonlar ve modül seviyesindeki sabitler."""
    defs: dict[str, tuple[str, set[str]]] = {}
    for name in RUNTIME_FILES:
        src = (HERE / name).read_text()
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.Assign)):
                seg = ast.get_source_segment(src, node)
                used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                if isinstance(node, ast.FunctionDef):
                    defs[node.name] = (seg, used)
                else:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            defs[t.id] = (seg, used)
    return defs


def _closure(entry_code: str) -> list[str]:
    defs = _definitions()
    want = {n.id for n in ast.walk(ast.parse(entry_code)) if isinstance(n, ast.Name)}
    seen: list[str] = []
    stack = [n for n in want if n in defs]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.append(name)
        stack.extend(n for n in defs[name][1] if n in defs and n not in seen)
    order = list(defs)  # dosyalardaki sıra: sabitler kullanılmadan önce tanımlı olur
    return sorted(seen, key=order.index)


def rt_literal(rt: dict) -> str:
    """RT'yi Python kaynağına güvenle gömülecek bir JSON metnine çevirir."""
    text = json.dumps(rt, ensure_ascii=False, sort_keys=True)
    text = text.replace("}}", "} }").replace("{{", "{ {")
    while "}}" in text or "{{" in text:
        text = text.replace("}}", "} }").replace("{{", "{ {")
    if json.loads(text) != json.loads(json.dumps(rt)):
        raise SnippetError("RT içindeki bir metin süslü parantez çifti içeriyor")
    return text


def _indent(code: str, n: int = 4) -> str:
    return "\n".join((" " * n + line) if line.strip() else line for line in code.strip("\n").splitlines())


def build_snippet(entry_code: str, rt: dict, fallback: str = "", template_args: list[str] | None = None) -> str:
    """Giriş kodunu ve ihtiyaç duyduğu fonksiyonları tek snippet'e paketler.

    `template_args`: sadece model-çağrılı code_exec tool'larında. Platform tool çağrısında `code` alanındaki
    şablonları argümanlarla çözüyorsa değer `ARG_<ad>` sabitine düşer; çözmüyorsa sabit boş sayılır
    (tool_arg() süslü parantez içeren değeri yok sayar). Güvenlik kontrolü bu satırlar eklenmeden önce yapılır.
    """
    defs = _definitions()
    parts = [HEADER, "RT = json.loads(" + repr(rt_literal(rt)) + ")\n"]
    for name in _closure(entry_code):
        parts.append(defs[name][0] + "\n")
    parts.append("try:\n" + _indent(entry_code) + "\nexcept Exception as _err:\n"
                 + "    try:\n        vars['runtime_error'] = str(_err)[:300]\n    except Exception:\n        pass\n"
                 + (_indent(fallback) + "\n" if fallback.strip() else ""))
    code = "\n".join(parts)
    if "{{" in code or "}}" in code:
        raise SnippetError("snippet içinde süslü parantez çifti var")
    if template_args:
        lines = "".join("ARG_%s = '''%s'''\n" % (a, "{" + "{" + a + "}" + "}") for a in template_args)
        code = HEADER + lines + code[len(HEADER):]
    compile(code, "<snippet>", "exec")
    return code


def run_snippet(code: str, **names) -> dict:
    """Testler ve yerel kontroller için: snippet'i verilen adlarla (vars, result, config) çalıştırır."""
    scope = dict(names)
    exec(compile(code, "<snippet>", "exec"), scope)
    return scope


def bundle_namespace(rt: dict | None = None) -> dict:
    """Bütün runtime fonksiyonlarını tek namespace'te yükler (birim testleri için)."""
    defs = _definitions()
    scope: dict = {}
    exec(HEADER, scope)
    if rt is not None:
        scope["RT"] = rt
    for name in defs:
        exec(defs[name][0], scope)
    return scope
