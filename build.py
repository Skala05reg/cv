"""Build two editable, single-page Russian resumes from resume_data.json.

Local only: reads JSON and bundled fonts; writes PDFs, text copies and a QA report.
Requires reportlab and pypdf. No network, background processes or font downloads.
Run build.cmd, or python build.py --only junior|senior. See README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfdoc import PDFString
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "pdf"
PUBLIC_OUTPUT = ROOT / "public"
FONT_DIR = ROOT / "assets" / "fonts"
PAGE_W, PAGE_H = A4
PUBLIC_FILENAMES = {
    "junior": "resume-1c.pdf",
    "senior": "resume-1c-developer.pdf",
}
PUBLIC_ALIASES = {
    "junior": ("resume-1c-junior.pdf",),
    "senior": ("resume-1c-senior.pdf",),
}


@dataclass
class Block:
    kind: str
    height: float
    data: object
    weight: float = 0.0


def normalized(value: str) -> str:
    # Use ASCII hyphens in all displayed text, including pasted Unicode dashes.
    return re.sub(r"[\u2010-\u2015\u2212]", "-", value).replace("\u00a0", " ")


def all_strings(obj):
    if isinstance(obj, str):
        yield normalized(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from all_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from all_strings(value)


def register_fonts():
    for weight in ("Regular", "SemiBold", "Bold"):
        path = FONT_DIR / f"IBMPlexSans-{weight}.ttf"
        if not path.is_file():
            raise ValueError(f"Не найден шрифт: {path}. Верните папку assets из комплекта.")
        pdfmetrics.registerFont(TTFont(f"Plex-{weight}", str(path)))
    pdfmetrics.registerFontFamily(
        "Plex-Regular", normal="Plex-Regular", bold="Plex-SemiBold",
        italic="Plex-Regular", boldItalic="Plex-SemiBold",
    )


def validate(data):
    if not all(isinstance(value, str) for value in data["person"].values()):
        raise ValueError('Поля person должны быть строками; для скрытия используйте "".')
    achievements = data.get("achievements", [])
    if not isinstance(achievements, list) or any(
        not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip()
                                             for k in ("title", "result"))
        for item in achievements
    ):
        raise ValueError('achievements должен быть списком объектов с непустыми строками title и result; [] скрывает блок.')
    for key, resume in data["resumes"].items():
        if not resume["jobs"] or not resume["skills"]:
            raise ValueError(f"В резюме {key} отсутствует опыт или навыки.")
        if Path(resume["filename"]).name != resume["filename"]:
            raise ValueError("filename должен содержать только имя PDF, без пути.")
        for job in resume["jobs"]:
            if not re.fullmatch(r"\d{2}\.\d{4}-\d{2}\.\d{4}", job["dates"]):
                raise ValueError("Даты работы должны иметь формат 06.2023-06.2024.")
    cmap = pdfmetrics.getFont("Plex-Regular").face.charToGlyph
    missing = sorted({ch for txt in all_strings(data) for ch in txt
                      if not ch.isspace() and ord(ch) not in cmap})
    if missing:
        raise ValueError("Шрифт не поддерживает символы: " + " ".join(missing))


def paragraph(text, width, size, leading, color, bold=False):
    style = ParagraphStyle(
        "resume", fontName="Plex-SemiBold" if bold else "Plex-Regular",
        fontSize=size, leading=leading, textColor=color, alignment=TA_LEFT,
        spaceBefore=0, spaceAfter=0, splitLongWords=False,
        allowWidows=0, allowOrphans=0,
    )
    p = Paragraph(text, style)
    _, height = p.wrap(width, 10000)
    return p, height


def plain(text):
    return escape(normalized(text))


def draw_icon(c, kind, x, y, size, color):
    """Original decorative line icons in a 24-unit grid; text remains separate."""
    c.saveState()
    c.translate(x, y)
    c.scale(size / 24, size / 24)
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.65)
    c.setLineCap(1)
    c.setLineJoin(1)

    def line(points, close=False):
        p = c.beginPath()
        p.moveTo(*points[0])
        for point in points[1:]:
            p.lineTo(*point)
        if close:
            p.close()
        c.drawPath(p, stroke=1, fill=0)

    if kind == "platform":
        c.roundRect(3, 7, 18, 14, 2, stroke=1, fill=0)
        line([(8, 3), (16, 3)])
        line([(12, 3), (12, 7)])
        line([(9, 17), (6, 14), (9, 11)])
        line([(15, 17), (18, 14), (15, 11)])
    elif kind == "database":
        c.ellipse(4, 15, 20, 21, stroke=1, fill=0)
        line([(4, 18), (4, 5)])
        line([(20, 18), (20, 5)])
        for v in (5, 11):
            p = c.beginPath()
            p.moveTo(4, v)
            p.curveTo(4, v - 4, 20, v - 4, 20, v)
            c.drawPath(p, stroke=1)
    elif kind == "exchange":
        line([(3, 16), (21, 16), (17, 20)])
        line([(21, 16), (17, 12)])
        line([(21, 7), (3, 7), (7, 11)])
        line([(3, 7), (7, 3)])
    elif kind == "git":
        for px, py in ((6, 4), (6, 20), (18, 17)):
            c.circle(px, py, 2.5, stroke=1, fill=0)
        line([(6, 6.5), (6, 17.5)])
        p = c.beginPath()
        p.moveTo(6, 8)
        p.curveTo(18, 8, 18, 11, 18, 14.5)
        c.drawPath(p, stroke=1)
    elif kind == "work":
        c.roundRect(2, 4, 20, 14, 2, stroke=1, fill=0)
        line([(8, 18), (8, 21), (16, 21), (16, 18)])
        line([(2, 12), (10, 10), (14, 10), (22, 12)])
        line([(12, 12), (12, 8)])
    elif kind == "education":
        line([(1, 15), (12, 21), (23, 15), (12, 9)], close=True)
        line([(6, 12), (6, 5), (12, 2), (18, 5), (18, 12)])
        line([(22, 14), (22, 5)])
    elif kind == "award":
        c.circle(12, 15, 6, stroke=1, fill=0)
        line([(8, 10), (6, 2), (11, 5), (12, 9)])
        line([(16, 10), (18, 2), (13, 5), (12, 9)])
        c.circle(12, 15, 2.5, stroke=1, fill=0)
    elif kind == "location":
        p = c.beginPath()
        p.moveTo(12, 2)
        p.curveTo(9, 6, 4, 10, 4, 15)
        p.curveTo(4, 25, 20, 25, 20, 15)
        p.curveTo(20, 10, 15, 6, 12, 2)
        c.drawPath(p, stroke=1)
        c.circle(12, 15, 2.7, stroke=1, fill=0)
    elif kind == "age":
        c.circle(12, 17, 4, stroke=1, fill=0)
        p = c.beginPath()
        p.moveTo(4, 3)
        p.curveTo(4, 13, 20, 13, 20, 3)
        c.drawPath(p, stroke=1)
    elif kind == "email":
        c.roundRect(2, 4, 20, 16, 2, stroke=1, fill=0)
        line([(3, 18), (12, 11), (21, 18)])
    elif kind == "telegram":
        line([(2, 12), (22, 21), (17, 2), (10, 8), (2, 12)], close=True)
        line([(10, 8), (18, 17)])
    elif kind == "phone":
        line([(4, 21), (9, 21), (10, 15), (7, 13), (11, 8),
              (15, 7), (17, 10), (22, 8), (21, 3)])
        p = c.beginPath()
        p.moveTo(21, 3)
        p.curveTo(10, 0, 0, 11, 4, 21)
        c.drawPath(p, stroke=1)
    c.restoreState()


def make_blocks(data, resume):
    cfg = data["layout"]
    palette = {k: colors.HexColor(v) for k, v in cfg["colors"].items()}
    margin = float(cfg["page_margin"])
    width = PAGE_W - 2 * margin
    rail = float(cfg.get("sidebar_width", 174))
    gutter = float(cfg.get("column_gap", 18))
    main_w = width - rail - gutter
    if rail < 140 or main_w < 280:
        raise ValueError("Слишком узкие колонки: проверьте sidebar_width и column_gap.")
    side_w = rail - 2 * float(cfg.get("sidebar_padding", 11))
    body, leading = cfg["body_size"], cfg["body_leading"]
    main, skills, education = [], [], []

    def para(target, text, w, size, line, color, bold=False, indent=0, bullet=False):
        parts = [part.strip() for part in str(text).split("\n") if part.strip()]
        for i, part in enumerate(parts):
            if i:
                target.append(Block("space", 4.2, None, .15))
            p, h = paragraph(plain(part), w - indent, size, line, color, bold)
            target.append(Block("bullet" if bullet else "paragraph", h, (p, indent), .35 if bullet else 0))

    def section(target, text, color, icon, height=23):
        target.append(Block("section", height, (text, color, icon), .25))

    section(skills, "НАВЫКИ И ТЕХНОЛОГИИ", palette["blue"], "platform", 25)
    for i, group in enumerate(resume["skills"]):
        if i:
            skills.append(Block("space", 6, None))
        skills.append(Block("skill_title", 16, (group["label"], group.get("icon", "platform"))))
        entries = group.get("items", [group.get("text", "")])
        if cfg.get("compact_skills", False):
            entries = [" · ".join(value for value in entries if value.strip())]
        for j, value in enumerate(entries):
            para(skills, value, side_w, cfg["skills_size"], cfg["skills_leading"], palette["ink"])
            if j < len(entries) - 1:
                skills.append(Block("space", .4, None))

    para(main, resume["summary"], main_w, body, leading, palette["ink"])
    main.append(Block("space", 6, None, .35))
    section(main, "ОПЫТ РАБОТЫ", palette["green"], "work", 22)
    for index, job in enumerate(resume["jobs"]):
        if index:
            main.append(Block("divider", 13, None, .3))
        para(main, job["company"], main_w, 11.1, 13.3,
             palette["placeholder"] if "[" in job["company"] else palette["ink"], True)
        main.append(Block("job_meta", 15, (job["role"], job["dates"])))
        if job.get("context"):
            para(main, job["context"], main_w, body - .15, leading - .25, palette["muted"])
            main.append(Block("space", 5, None, .2))
        for i, bullet in enumerate(job["bullets"]):
            para(main, bullet, main_w, body, leading, palette["ink"], indent=9, bullet=True)
            if i < len(job["bullets"]) - 1:
                main.append(Block("space", 2, None, .25))

    section(education, "ОБРАЗОВАНИЕ", palette["ochre"], "education", 24)
    for i, edu in enumerate(data["education"]):
        if i:
            education.append(Block("space", 8, None))
        para(education, edu["dates"], side_w, 8.9, 11.3, palette["ochre"], True)
        para(education, edu["school"], side_w, cfg["education_size"], cfg["education_leading"], palette["ink"], True)
        para(education, edu["program"], side_w, cfg["education_size"], cfg["education_leading"], palette["muted"])
        if edu.get("details"):
            para(education, edu["details"], side_w, cfg["education_size"], cfg["education_leading"], palette["muted"])
    achievements = data.get("achievements", [])
    if achievements:
        education.append(Block("space", 10, None))
        section(education, "ДОСТИЖЕНИЯ", palette["ochre"], "award", 24)
        for i, achievement in enumerate(achievements):
            if i:
                education.append(Block("space", 5, None))
            text = plain(achievement["title"]) + " - <b>" + plain(achievement["result"]) + "</b>"
            p, h = paragraph(text, side_w, cfg["education_size"], cfg["education_leading"], palette["ink"])
            education.append(Block("paragraph", h, (p, 0)))
    return main, skills, education, palette, margin, width, rail, gutter


def draw_blocks(c, blocks, x, width, top, palette, icons, spread=0):
    y = top
    geometry = []
    for block in blocks:
        h = block.height
        if block.kind in ("paragraph", "bullet"):
            p, indent = block.data
            p.drawOn(c, x + indent, y - h)
            if block.kind == "bullet":
                c.setFillColor(palette["green"])
                c.circle(x + 2, y - 6, 1.3, fill=1, stroke=0)
        elif block.kind == "section":
            label, color, icon = block.data
            offset = 17 if icons else 0
            if icons:
                draw_icon(c, icon, x, y - 12, 11, color)
            c.setFillColor(color)
            c.setFont("Plex-SemiBold", 8.4 if width < 200 else 9.5)
            c.drawString(x + offset, y - 10, label)
            c.setStrokeColor(palette["rule"])
            c.setLineWidth(.5)
            c.line(x, y - 16, x + width, y - 16)
        elif block.kind == "skill_title":
            label, icon = block.data
            if icons:
                draw_icon(c, icon, x, y - 11, 10, palette["blue"])
            c.setFont("Plex-SemiBold", 9.6)
            c.setFillColor(palette["blue"])
            c.drawString(x + (16 if icons else 0), y - 9, normalized(label))
        elif block.kind == "job_meta":
            role, dates = block.data
            c.setFont("Plex-Regular", 9.2)
            c.setFillColor(palette["green"])
            c.drawString(x, y - 10, normalized(role))
            date_w = pdfmetrics.stringWidth(dates, "Plex-Regular", 8.7)
            c.setFillColor(palette["header_bg"])
            c.roundRect(x + width - date_w - 10, y - 13, date_w + 10, 14, 3, stroke=0, fill=1)
            c.setFont("Plex-Regular", 8.7)
            c.setFillColor(palette["muted"])
            c.drawRightString(x + width - 5, y - 9.5, dates)
        elif block.kind == "divider":
            c.setStrokeColor(palette["rule"])
            c.setLineWidth(.5)
            c.line(x, y - h / 2, x + width, y - h / 2)
        if block.kind not in ("space", "divider"):
            geometry.append({"kind": block.kind, "left": round(x, 2), "width": round(width, 2),
                             "top": round(y, 2), "bottom": round(y - h, 2)})
        y -= h + block.weight * spread
    return y, geometry


def header(c, data, resume, palette, margin, width):
    person = data["person"]
    cfg = data["layout"]
    icons = cfg.get("show_icons", True)
    badge = cfg.get("show_1c_badge", True)
    c.setFillColor(palette["blue"])
    c.roundRect(margin, PAGE_H - 15, 54, 2.5, 1.5, fill=1, stroke=0)
    if badge:
        bx, by = margin + width - 50, PAGE_H - 76
        c.setFillColor(palette["badge_bg"])
        c.roundRect(bx, by, 50, 50, 10, stroke=0, fill=1)
        c.setFillColor(palette["badge_ink"])
        c.setFont("Plex-Bold", 26)
        c.drawCentredString(bx + 25, by + 15, "1С")
    y = PAGE_H - 26
    name_width = width - (68 if badge else 0)
    name = normalized(person.get("name", "").strip())
    size = 24
    while pdfmetrics.stringWidth(name, "Plex-SemiBold", size) > name_width and size > 18:
        size -= .5
    if name:
        p, h = paragraph(plain(name), name_width, size, size + 1,
                         palette["placeholder"] if "[" in name else palette["ink"], bold=True)
        p.drawOn(c, margin, y - h)
        y -= h + 1
    p, h = paragraph(plain(resume["title"]), name_width, 15, 18, palette["blue"])
    p.drawOn(c, margin, y - h)
    y -= h + 3
    level_line = " · ".join(v for v in (resume["level"].strip(), resume["experience_label"].strip(), person.get("work_format", "").strip()) if v)
    if level_line:
        p, h = paragraph(plain(level_line), width, 9.3, 11.5, palette["muted"])
        p.drawOn(c, margin, y - h)
        y -= h + 4
    # Contact labels remain text; icons only help scanning. Empty fields take no space.
    cx, line_h = margin, 12
    populated = [(k, normalized(person.get(k, "").strip()))
                 for k in ("location", "age", "phone", "email", "telegram")
                 if person.get(k, "").strip()]
    row_top = y
    for key, value in populated:
        text_w = pdfmetrics.stringWidth(value, "Plex-Regular", 9.2)
        prefix = 13 if icons else 0
        item_w = text_w + prefix
        if item_w > width:
            raise ValueError(f"Поле person.{key} слишком длинное для строки контактов.")
        if cx > margin and cx + item_w > margin + width:
            cx = margin
            y -= line_h + 3
        if icons:
            draw_icon(c, key, cx, y - 10.5, 9, palette["blue"])
        c.setFont("Plex-Regular", 9.2)
        c.setFillColor(palette["placeholder"] if "[" in value else palette["muted"])
        c.drawString(cx + prefix, y - 9.2, value)
        rect = (cx, y - line_h, cx + item_w, y + 1)
        if key == "email" and "@" in value and "[" not in value:
            c.linkURL("mailto:" + value, rect, relative=0, thickness=0)
        elif key == "telegram" and value.startswith("@") and "[" not in value:
            c.linkURL("https://t.me/" + value[1:], rect, relative=0, thickness=0)
        cx += item_w + 15
    if populated:
        y -= line_h
    y -= 9
    c.setStrokeColor(palette["rule"])
    c.setLineWidth(.6)
    c.line(margin, y, margin + width, y)
    return y - 7


def render_resume(data, resume):
    main, skills, education, palette, margin, width, rail, gutter = make_blocks(data, resume)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    author = normalized(data["person"].get("name", "").strip())
    c.setTitle(" | ".join(v for v in (author, normalized(resume["title"])) if v))
    c.setAuthor(author)
    c.setSubject(normalized(resume["level"]))
    c.setKeywords("1С, 1C, разработчик, ERP, УТ, КА, СКД, БСП")
    c._doc.Catalog.Lang = PDFString("ru-RU")
    top = header(c, data, resume, palette, margin, width)
    available = top - margin
    main_h = sum(b.height for b in main)
    skills_h = sum(b.height for b in skills)
    education_h = sum(b.height for b in education)
    side_h = skills_h + education_h + 18
    overflow = max(main_h, side_h) - available
    if overflow > .01:
        raise ValueError(
            f'{resume["filename"]}: текст превышает одну страницу на {overflow:.1f} pt '
            f'(опыт: {main_h:.1f}, боковая колонка: {side_h:.1f}, доступно: {available:.1f}). '
            'Сократите текст в resume_data.json. Размер шрифта автоматически не уменьшается.'
        )
    icons = data["layout"].get("show_icons", True)
    c.setFillColor(palette["skills_bg"])
    c.roundRect(margin, margin, rail, available + 5, 7, stroke=0, fill=1)
    # Draw semantic order explicitly: skills, main profile/experience, education.
    padding = float(data["layout"].get("sidebar_padding", 11))
    _, g1 = draw_blocks(c, skills, margin + padding, rail - 2 * padding, top - 2, palette, icons)
    weights = sum(b.weight for b in main)
    spread = min((available - main_h) / max(weights, 1), 12.0)
    y, g2 = draw_blocks(c, main, margin + rail + gutter, width - rail - gutter,
                        top, palette, icons, spread)
    edu_top = margin + education_h + 8
    _, g3 = draw_blocks(c, education, margin + padding, rail - 2 * padding, edu_top, palette, icons)
    geometry = g1 + g2 + g3
    c.showPage()
    c.save()
    result = buffer.getvalue()
    reader = PdfReader(BytesIO(result))
    if len(reader.pages) != 1:
        raise ValueError("Внутренняя ошибка: PDF должен иметь одну страницу.")
    extracted = normalized(reader.pages[0].extract_text())
    compact = lambda text: re.sub(r"\s+", "", normalized(text))
    required = [resume["title"], "НАВЫКИ И ТЕХНОЛОГИИ", "ОПЫТ РАБОТЫ", "ОБРАЗОВАНИЕ"]
    required.extend(job["dates"] for job in resume["jobs"])
    required.extend(job["company"] for job in resume["jobs"])
    for group in resume["skills"]:
        required.append(group["label"])
        required.extend(group.get("items") or [group.get("text", "")])
    for education in data.get("education", []):
        required.extend((education.get("school", ""), education.get("program", "")))
    if data.get("achievements"):
        required.append("ДОСТИЖЕНИЯ")
    for achievement in data.get("achievements", []):
        required.extend((achievement["title"], achievement["result"]))
    for item in required:
        if compact(item) not in compact(extracted):
            raise ValueError(f"В тексте PDF отсутствует: {item}")
    if any(ch in reader.pages[0].extract_text() for ch in ("\u2014", "\ufffd", "\u25a0")):
        raise ValueError("В PDF найдено длинное тире или повреждённый символ.")
    jobs_in_text = [compact(extracted).find(compact(job["company"])) for job in resume["jobs"]]
    if -1 in jobs_in_text or jobs_in_text != sorted(jobs_in_text):
        raise ValueError("Порядок работодателей при извлечении текста нарушен.")
    section_order_ok = extracted.index("НАВЫКИ И ТЕХНОЛОГИИ") < extracted.index("ОПЫТ РАБОТЫ") < extracted.index("ОБРАЗОВАНИЕ")
    if not section_order_ok:
        raise ValueError("Порядок разделов при извлечении текста нарушен.")
    return result, extracted, {
        "pages": 1,
        "body_font_pt": data["layout"]["body_size"],
        "content_bottom_pt": round(y, 2),
        "bottom_margin_pt": margin,
        "remaining_whitespace_pt": round(y - margin, 2),
        "section_order_ok": section_order_ok,
        "required_text_ok": True,
        "placeholders": sorted(set(re.findall(r"\[[^\]\n]+\]", extracted))),
        "blocks": geometry,
    }


def main():
    parser = argparse.ArgumentParser(description="Сборка резюме 1С из редактируемого JSON")
    parser.add_argument("--only", choices=("junior", "senior"))
    args = parser.parse_args()
    data = json.loads((ROOT / "resume_data.json").read_text(encoding="utf-8-sig"))
    register_fonts()
    validate(data)
    keys = [args.only] if args.only else list(data["resumes"])
    # Render and validate every selected PDF in memory before replacing outputs.
    prepared = [(key, render_resume(data, data["resumes"][key])) for key in keys]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUTPUT.mkdir(parents=True, exist_ok=True)
    reports = {}
    for key, (pdf_bytes, extracted, report) in prepared:
        filename = data["resumes"][key]["filename"]
        target = OUTPUT / filename
        temporary = target.with_suffix(".pdf.tmp")
        temporary.write_bytes(pdf_bytes)
        try:
            temporary.replace(target)
        except PermissionError:
            target = target.with_name(target.stem + " - обновлено.pdf")
            temporary.replace(target)
            print("Основной PDF недоступен для замены; сохранена обновлённая копия. "
                  "Закройте основной PDF перед следующей сборкой для обновления его обычного имени.")
        report["output_filename"] = target.name
        public_name = PUBLIC_FILENAMES[key]
        (PUBLIC_OUTPUT / public_name).write_bytes(pdf_bytes)
        for alias in PUBLIC_ALIASES.get(key, ()):
            (PUBLIC_OUTPUT / alias).write_bytes(pdf_bytes)
        report["public_filename"] = public_name
        (OUTPUT / f"{key}.txt").write_text(extracted, encoding="utf-8")
        (PUBLIC_OUTPUT / f"{key}.txt").write_text(extracted, encoding="utf-8")
        reports[key] = report
        print(f"Создано: {target}")
        print(f"Публичная копия: {PUBLIC_OUTPUT / public_name}")
        print(f'1 страница; основной шрифт {report["body_font_pt"]} pt; '
              f'свободное место над нижним полем {report["remaining_whitespace_pt"]} pt')
        if report["placeholders"]:
            print("Заполните поля: " + ", ".join(report["placeholders"]))
    (OUTPUT / "verification.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(f"Ошибка сборки: {error}", file=sys.stderr)
        raise SystemExit(1)
