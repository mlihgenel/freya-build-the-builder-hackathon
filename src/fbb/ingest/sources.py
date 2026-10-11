"""Brief dosyalarını okur. Birden fazla dosya verilirse sırası önemlidir: sonraki dosya öncekini değiştirir.

Bir klasör verilirse içindeki bütün belgeler (Markdown, metin, Word, PDF, Excel, CSV, JSON) okunur; README/BRIEF önce,
gerisi ada göre sıralı. Word ve Excel, ek kütüphane olmadan zip içindeki XML'den okunur.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

DOC_SUFFIXES = (".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xlsm", ".csv", ".json", ".yaml", ".yml")


def _xml_text(xml: str) -> str:
    xml = re.sub(r"</w:p>|<w:br/>|<w:tab/>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = ["word/document.xml"] + sorted(n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml", n))
        out = []
        for n in names:
            if n in z.namelist():
                xml = z.read(n).decode("utf-8", "replace")
                # tablo hücreleri: hücre sonuna ayraç
                xml = xml.replace("</w:tc>", " | </w:tc>").replace("</w:tr>", "</w:tr>\n")
                out.append(_xml_text(xml))
    text = "\n".join(out)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_xlsx(path: Path) -> str:
    """Her sayfa: satırlar, hücreler ' | ' ile."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            for si in re.findall(r"<si>(.*?)</si>", xml, re.S):
                shared.append("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
        names = {}
        if "xl/workbook.xml" in z.namelist():
            wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
            for i, m in enumerate(re.finditer(r'<sheet [^>]*name="([^"]+)"', wb), 1):
                names[i] = m.group(1)
        out = []
        sheets = sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for n in sheets:
            idx = int(re.findall(r"\d+", n)[-1])
            xml = z.read(n).decode("utf-8", "replace")
            out.append(f"--- sheet: {names.get(idx, idx)} ---")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
                cells = []
                for attrs, body in re.findall(r"<c([^>]*?)(?:/>|>(.*?)</c>)", row, re.S):
                    v = re.search(r"<v>(.*?)</v>", body or "", re.S)
                    t = re.search(r'\bt="(\w+)"', attrs)
                    if t and t.group(1) == "s" and v:
                        cells.append(shared[int(v.group(1))] if int(v.group(1)) < len(shared) else "")
                    elif t and t.group(1) == "inlineStr":
                        cells.append("".join(re.findall(r"<t[^>]*>(.*?)</t>", body or "", re.S)))
                    else:
                        cells.append(v.group(1) if v else "")
                if any(c.strip() for c in cells):
                    out.append(" | ".join(cells))
    text = "\n".join(out)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages).strip()


def read_document(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".docx":
        return read_docx(path)
    if suf in (".xlsx", ".xlsm"):
        return read_xlsx(path)
    if suf == ".pdf":
        return read_pdf(path)
    if suf == ".csv":
        rows = list(csv.reader(io.StringIO(path.read_text(errors="replace"))))
        return "\n".join(" | ".join(r) for r in rows)
    return path.read_text(errors="replace").strip()


def is_openapi(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    return isinstance(data, dict) and "paths" in data and ("openapi" in data or "swagger" in data)


def expand(paths: list[str | Path]) -> list[Path]:
    """Klasörleri belge listesine açar (README/BRIEF önce, gerisi ada göre). Gizli dosyalar ve openapi atlanır."""
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.is_dir():
            out.append(path)
            continue
        docs = [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in DOC_SUFFIXES
                and not any(part.startswith((".", "__MACOSX")) for part in f.relative_to(path).parts)
                and not is_openapi(f)]

        def key(f: Path, root: Path = path):
            name = f.name.lower()
            first = 0 if name.startswith("brief") else 1 if name.startswith("readme") else 2
            return first, str(f.relative_to(root)).lower()

        out.extend(sorted(docs, key=key))
    return out


def read_sources(paths: list[str | Path]) -> str:
    files = expand(paths)
    parts = []
    for i, path in enumerate(files, 1):
        try:
            text = read_document(path)
        except Exception as e:  # okunamayan belge build'i durdurmaz
            text = f"[could not read this file: {e}]"
        parts.append(f"===== DOCUMENT {i} of {len(files)}: {path.name} =====\n{text}\n")
    if len(files) > 1:
        parts.append("NOTE: these documents together describe the case. Where a later document, announcement or memo "
                     "changes an earlier one, the change wins.")
    return "\n".join(parts)


def find_openapi(paths: list[str | Path]) -> Path | None:
    for p in paths:
        path = Path(p)
        cands = [path] if path.is_file() else sorted(path.rglob("*.json")) if path.is_dir() else []
        for f in cands:
            if is_openapi(f):
                return f
    return None


def slot_for(paths: list[str | Path]) -> str:
    """Workflow slot adı: son brief dosyasının (ya da klasörün) adı."""
    return Path(paths[-1]).stem
