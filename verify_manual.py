from docx import Document

doc = Document(r"c:\Users\Admini503\.openclaw\workspace\车辆清洗智能识别系统产品说明书_temp.docx")
print(f"段落总数: {len(doc.paragraphs)}")
print(f"表格总数: {len(doc.tables)}")

# 查找设备清单相关内容
found = False
for i, para in enumerate(doc.paragraphs):
    if '硬件设备清单' in para.text or '2.4' in para.text:
        print(f"段落 {i}: {para.text}")
        found = True

# 查看最后几个表格的内容
print("\n最后插入的表格内容：")
if doc.tables:
    last_table = doc.tables[-1]
    for row in last_table.rows:
        cells = [cell.text.replace('\n', ' | ') for cell in row.cells]
        print(cells)
