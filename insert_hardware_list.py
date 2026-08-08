# -*- coding: utf-8 -*-
"""
将 Excel 硬件设备清单插入到产品说明书中。
插入位置：第 2 章“系统组成”末尾，第 3 章之前。
"""

import pandas as pd
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

EXCEL_PATH = r"c:\Users\Admini503\.openclaw\workspace\车辆识别智慧工地硬件设备(2).xlsx"
DOCX_PATH = r"c:\Users\Admini503\.openclaw\workspace\车辆清洗智能识别系统产品说明书.docx"
OUTPUT_PATH = r"c:\Users\Admini503\.openclaw\workspace\车辆清洗智能识别系统产品说明书.docx"
TEMP_PATH = r"c:\Users\Admini503\.openclaw\workspace\车辆清洗智能识别系统产品说明书_temp.docx"


def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)


def read_hardware_list():
    df = pd.read_excel(EXCEL_PATH, sheet_name='Sheet1', header=None)
    # 去掉完全空行/空列
    df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
    values = df.values.tolist()
    # 原始表格结构：
    # 第1行通常是标题 "车辆AI识别系统"
    # 第2行开始是设备数据
    # 列大致为：序号、设备名称、规格参数、数量、单位、单价
    # 由于原表头不规则，这里手动构造表头，并取后面的数据行
    records = []
    for row in values:
        # 跳过表头标题行
        if str(row[0]).strip() in ['车辆AI识别系统', '车辆AI识别系统 ']:
            continue
        # 如果第一列不是数字，也跳过
        try:
            idx = int(row[0])
        except (ValueError, TypeError):
            continue
        name = str(row[1]) if pd.notna(row[1]) else ''
        spec = str(row[2]) if len(row) > 2 and pd.notna(row[2]) else ''
        qty = str(int(row[3])) if len(row) > 3 and pd.notna(row[3]) else ''
        unit = str(row[4]) if len(row) > 4 and pd.notna(row[4]) else ''
        price = str(int(row[5])) if len(row) > 5 and pd.notna(row[5]) else ''
        records.append([idx, name, spec, qty, unit, price])
    return records


def format_spec_text(spec):
    """将规格中的 \n 替换为便于阅读的换行，并清理多余空格"""
    return spec.replace('\\n', '\n').replace('\n', '\n')


def insert_hardware_section():
    records = read_hardware_list()
    if not records:
        print("未读取到设备清单数据")
        return

    doc = Document(DOCX_PATH)

    # 找到第 3 章“功能说明”所在段落，在其前面插入设备清单
    target_para = None
    for para in doc.paragraphs:
        if para.text.strip().startswith('3. 功能说明'):
            target_para = para
            break

    if target_para is None:
        print("未找到 '3. 功能说明' 插入位置，请检查文档结构")
        return

    # 插入 2.4 小节标题
    heading = target_para.insert_paragraph_before('2.4 硬件设备清单', style='Heading 2')
    for run in heading.runs:
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(0, 102, 153)
        run.font.bold = True
    heading.paragraph_format.space_before = Pt(16)
    heading.paragraph_format.space_after = Pt(8)

    # 插入说明文字
    desc = target_para.insert_paragraph_before(
        '本系统所需的主要硬件设备清单如下，实际采购数量和型号可根据项目现场需求进行调整。'
    )
    desc.paragraph_format.first_line_indent = Cm(0.74)
    desc.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    desc.paragraph_format.space_after = Pt(6)
    for run in desc.runs:
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0, 0, 0)

    # 插入表格
    table = doc.add_table(rows=len(records) + 1, cols=6)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 设置列宽
    col_widths = [1.5, 3.5, 7, 1.5, 1.5, 2]
    for i, width in enumerate(col_widths):
        for cell in table.columns[i].cells:
            cell.width = Cm(width)

    headers = ['序号', '设备名称', '规格参数', '数量', '单位', '单价（元）']
    hdr_cells = table.rows[0].cells
    for i, text in enumerate(headers):
        hdr_cells[i].text = text
        set_cell_shading(hdr_cells[i], 'E7E6E6')
        hdr_cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for paragraph in hdr_cells[i].paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.space_before = Pt(3)
            for run in paragraph.runs:
                run.font.name = 'Microsoft YaHei'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
                run.font.size = Pt(10.5)
                run.font.bold = True

    # 填充数据
    for row_idx, rec in enumerate(records, start=1):
        cells = table.rows[row_idx].cells
        for col_idx, val in enumerate(rec):
            cells[col_idx].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            # 规格参数列保留换行
            if col_idx == 2:
                cells[col_idx].text = format_spec_text(str(val))
            else:
                cells[col_idx].text = str(val)
            for paragraph in cells[col_idx].paragraphs:
                paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                paragraph.paragraph_format.space_after = Pt(3)
                paragraph.paragraph_format.space_before = Pt(3)
                # 序号、数量、单位、单价居中；名称和规格左对齐
                if col_idx in [0, 3, 4, 5]:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.name = 'Microsoft YaHei'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
                    run.font.size = Pt(10.5)

    # 将表格移动到目标段落之前（add_table 默认加在文档末尾，需要移动）
    # python-docx 没有直接移动表格的 API，但可以通过在目标段落前插入一个段落，
    # 然后将表格添加到这个段落之后来实现。这里采用另一种方式：
    # 由于 add_table 会添加到 body 末尾，而目标段落在前面，我们可以利用 _element 操作。
    # 更简单的方法：直接在目标段落前插入占位段落，然后将表格元素插入到占位段落之前。
    placeholder = target_para.insert_paragraph_before('')
    placeholder._p.addnext(table._tbl)
    placeholder._element.getparent().remove(placeholder._element)

    # 先保存到临时文件，再替换原文件，避免原文件被占用时报错
    doc.save(TEMP_PATH)
    import shutil
    import os
    # 如果原文件存在且被占用，尝试先删除再移动
    max_retries = 5
    for attempt in range(max_retries):
        try:
            if os.path.exists(OUTPUT_PATH):
                os.remove(OUTPUT_PATH)
            shutil.move(TEMP_PATH, OUTPUT_PATH)
            break
        except PermissionError:
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
            else:
                # 若始终无法替换，保留临时文件并告知用户
                print(f"原文件被占用，已保存为临时文件：{TEMP_PATH}")
                print(f"请关闭打开中的 Word 文档后，将临时文件重命名为：{OUTPUT_PATH}")
                return
    print(f"设备清单已插入：{OUTPUT_PATH}")
    print(f"共插入 {len(records)} 条设备记录")


if __name__ == '__main__':
    insert_hardware_section()
