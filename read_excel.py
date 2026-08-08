import pandas as pd

file = r"c:\Users\Admini503\.openclaw\workspace\车辆识别智慧工地硬件设备(2).xlsx"
xl = pd.ExcelFile(file)
print("Sheets:", xl.sheet_names)
for sheet in xl.sheet_names:
    df = pd.read_excel(file, sheet_name=sheet)
    print(f"\n=== Sheet: {sheet} ===")
    print(df.to_string(index=False))
    print(f"Shape: {df.shape}")
