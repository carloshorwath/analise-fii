import filecmp
import os

def compare_dirs(dir1, dir2, ignore_list):
    dcmp = filecmp.dircmp(dir1, dir2, ignore=ignore_list)
    
    diff = {
        'left_only': dcmp.left_only,
        'right_only': dcmp.right_only,
        'diff_files': dcmp.diff_files,
        'subdirs': {}
    }
    
    for common_dir in dcmp.common_dirs:
        sub_diff = compare_dirs(os.path.join(dir1, common_dir), os.path.join(dir2, common_dir), ignore_list)
        if any(sub_diff.values()):
            diff['subdirs'][common_dir] = sub_diff
            
    return diff

def print_diff(diff, path=""):
    for f in diff.get('left_only', []):
        print(f"Added in V3: {os.path.join(path, f)}")
    for f in diff.get('right_only', []):
        print(f"Removed in V3 (exists in V2): {os.path.join(path, f)}")
    for f in diff.get('diff_files', []):
        print(f"Modified: {os.path.join(path, f)}")
        
    for sub, sub_diff in diff.get('subdirs', {}).items():
        print_diff(sub_diff, os.path.join(path, sub))

ignore = ['.git', '__pycache__', 'analise-de-acoes-v2', '.env', '.venv', 'venv', 'node_modules', '.claude']
print("Comparing V3 (D:\\analise-de-acoes-v3) with V2 (D:\\analise-de-acoes-v3\\analise-de-acoes-v2)...")
diff_result = compare_dirs("D:\\analise-de-acoes-v3", "D:\\analise-de-acoes-v3\\analise-de-acoes-v2", ignore)
print_diff(diff_result)
