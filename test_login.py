import sys
import logging
from realm_client import get_credentials, get_config, login

logging.basicConfig(level=logging.DEBUG)

def main():
    cfg = get_config()
    username, password = get_credentials()
    try:
        session = login(cfg, username, password)
        print("Login successful!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
