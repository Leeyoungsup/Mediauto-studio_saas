#!/usr/bin/env python3
"""Build simple DOCX files from the patent HTML drafts.

This intentionally uses only the Python standard library because pandoc and
python-docx are not guaranteed to be installed on the production workstation.
The generated DOCX is plain but valid enough for Word/LibreOffice editing.
"""

from __future__ import annotations

import html
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SRC_DIR = Path(__file__).resolve().parent / "docx_src"
OUT_DIR = Path(__file__).resolve().parent / "docx"


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class PatentHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, Any]] = []
        self._stack: list[str] = []
        self._text_parts: list[str] = []
        self._list_stack: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._stack.append(tag)
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self._text_parts = []
        elif tag in {"ul", "ol"}:
            self._list_stack.append(tag)
        elif tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "p"}:
            text = _clean("".join(self._text_parts))
            if text:
                self.blocks.append({"type": tag, "text": text})
            self._text_parts = []
        elif tag == "li":
            text = _clean("".join(self._text_parts))
            if text:
                list_type = self._list_stack[-1] if self._list_stack else "ul"
                self.blocks.append({"type": "li", "list": list_type, "text": text})
            self._text_parts = []
        elif tag in {"ul", "ol"}:
            if self._list_stack:
                self._list_stack.pop()
        elif tag in {"td", "th"}:
            if self._row is not None and self._cell_parts is not None:
                self._row.append(_clean("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag == "tr":
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table:
                self.blocks.append({"type": "table", "rows": self._table})
            self._table = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        elif tag in self._stack:
            self._stack.remove(tag)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._cell_parts is not None:
            self._cell_parts.append(data)
            return
        if self._stack and self._stack[-1] in {"h1", "h2", "h3", "p", "li"}:
            self._text_parts.append(data)


def parse_html(path: Path) -> list[dict[str, Any]]:
    parser = PatentHtmlParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.blocks


def parse_markdown(path: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    para_parts: list[str] = []

    def flush_para() -> None:
        if para_parts:
            text = _clean(" ".join(para_parts))
            if text:
                blocks.append({"type": "p", "text": text})
            para_parts.clear()

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            flush_para()
            continue
        if line.startswith("# "):
            flush_para()
            blocks.append({"type": "h1", "text": _clean(line[2:])})
        elif line.startswith("## "):
            flush_para()
            blocks.append({"type": "h2", "text": _clean(line[3:])})
        elif line.startswith("### "):
            flush_para()
            blocks.append({"type": "h3", "text": _clean(line[4:])})
        elif line.startswith("- "):
            flush_para()
            blocks.append({"type": "li", "list": "ul", "text": _clean(line[2:])})
        elif re.match(r"^\d+\.\s+", line):
            flush_para()
            blocks.append({"type": "li", "list": "ol", "text": _clean(re.sub(r"^\d+\.\s+", "", line))})
        else:
            para_parts.append(line)
    flush_para()
    return blocks


def paragraph(text: str, style: str | None = None, *, bullet: bool = False, numbered: bool = False) -> str:
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if bullet:
        ppr += '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    if numbered:
        ppr += '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
    ppr_xml = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
    return f"<w:p>{ppr_xml}<w:r><w:t xml:space=\"preserve\">{_esc(text)}</w:t></w:r></w:p>"


def table(rows: list[list[str]]) -> str:
    grid_cols = max((len(row) for row in rows), default=1)
    grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(grid_cols))
    row_xml = []
    for row in rows:
        cells = []
        for cell in row:
            cells.append(
                "<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr>"
                f"{paragraph(cell or ' ')}"
                "</w:tc>"
            )
        while len(cells) < grid_cols:
            cells.append("<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr><w:p/></w:tc>")
        row_xml.append("<w:tr>" + "".join(cells) + "</w:tr>")
    return (
        "<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "<w:tblBorders><w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "<w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "<w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"777777\"/>"
        "</w:tblBorders></w:tblPr><w:tblGrid>"
        + grid
        + "</w:tblGrid>"
        + "".join(row_xml)
        + "</w:tbl>"
    )


def document_xml(blocks: list[dict[str, Any]]) -> str:
    body_parts = []
    for block in blocks:
        typ = block["type"]
        if typ == "h1":
            body_parts.append(paragraph(block["text"], "Title"))
        elif typ == "h2":
            body_parts.append(paragraph(block["text"], "Heading1"))
        elif typ == "h3":
            body_parts.append(paragraph(block["text"], "Heading2"))
        elif typ == "p":
            body_parts.append(paragraph(block["text"]))
        elif typ == "li":
            body_parts.append(paragraph(block["text"], bullet=block.get("list") == "ul", numbered=block.get("list") == "ol"))
        elif typ == "table":
            body_parts.append(table(block["rows"]))
    body_parts.append(
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body_parts)
        + "</w:body></w:document>"
    )


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="360"/></w:pPr>
    <w:rPr><w:b/><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="40"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="360" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="30"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:b/><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="25"/></w:rPr>
  </w:style>
</w:styles>
"""

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
  <w:abstractNum w:abstractNumId="2">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>
"""


def write_docx(src: Path, dst: Path) -> None:
    blocks = parse_html(src)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/document.xml", document_xml(blocks))
        zf.writestr("word/styles.xml", STYLES)
        zf.writestr("word/numbering.xml", NUMBERING)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(SRC_DIR.glob("*.html"))
    if not sources:
        print(f"No HTML sources found in {SRC_DIR}", file=sys.stderr)
        return 1
    for src in sources:
        dst = OUT_DIR / f"{src.stem}.docx"
        write_docx(src, dst)
        print(dst)
    md_src = Path(__file__).resolve().parent / "patent_candidates.md"
    if md_src.exists():
        dst = OUT_DIR / "patent_candidates.docx"
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", CONTENT_TYPES)
            zf.writestr("_rels/.rels", ROOT_RELS)
            zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
            zf.writestr("word/document.xml", document_xml(parse_markdown(md_src)))
            zf.writestr("word/styles.xml", STYLES)
            zf.writestr("word/numbering.xml", NUMBERING)
        print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
