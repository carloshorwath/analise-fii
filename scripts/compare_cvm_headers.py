import zipfile
import pandas as pd
import io

years = [2021, 2022, 2023]
file_types = ['complemento', 'geral']
results = {}

for year in years:
    zip_path = f'dados/cvm/raw/inf_mensal_fii_{year}.zip'
    results[year] = {}
    with zipfile.ZipFile(zip_path, 'r') as z:
        for ftype in file_types:
            filename = f'inf_mensal_fii_{ftype}_{year}.csv'
            try:
                with z.open(filename) as f:
                    # Read only headers
                    df = pd.read_csv(f, sep=';', encoding='latin1', nrows=0)
                    results[year][ftype] = list(df.columns)
                    print(f"Read {len(df.columns)} columns for {year} {ftype}")
            except KeyError:
                print(f"File {filename} not found in {zip_path}")

print("\n--- COMPARISON ---")
for ftype in file_types:
    print(f"\nFile type: {ftype}")
    h21 = set(results[2021].get(ftype, []))
    h22 = set(results[2022].get(ftype, []))
    h23 = set(results[2023].get(ftype, []))
    
    all_cols = sorted(list(h21 | h22 | h23))
    
    print(f"{'Column Name':<60} | 2021 | 2022 | 2023")
    print("-" * 80)
    for col in all_cols:
        v21 = "X" if col in h21 else " "
        v22 = "X" if col in h22 else " "
        v23 = "X" if col in h23 else " "
        if not (v21 == v22 == v23 == "X"):
            print(f"{col:<60} |  {v21}   |  {v22}   |  {v23}")

    # Summary of differences
    diff_21_22 = h21 ^ h22
    diff_22_23 = h22 ^ h23
    
    if not diff_21_22 and not diff_22_23:
        print("No differences found.")
    else:
        if diff_21_22:
            print(f"\nDifferences 2021 vs 2022: {diff_21_22}")
        if diff_22_23:
            print(f"Differences 2022 vs 2023: {diff_22_23}")
