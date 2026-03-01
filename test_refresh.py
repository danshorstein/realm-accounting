import sys
import logging
from data_loader import refresh_data

logging.basicConfig(level=logging.DEBUG)

def main():
    try:
        df = refresh_data()
        print("Refresh successful, rows:", len(df))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
