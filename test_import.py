import sys
import os

# Ensure src is in the path if needed, but the imports use 'src.' prefix
# sys.path.append(os.getcwd())

try:
    from src.fii_analysis.features import fundamentos
    print("Success")
except ImportError as e:
    print(f"ImportError: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
