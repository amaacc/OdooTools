import base64
import json
from cryptography.fernet import Fernet

# Obfuscated key parts (split into byte segments to prevent simple binary string extraction)
_K_PART1 = b"RD4rpXJk1OegsLt"
_K_PART2 = b"7ZvZTFgpqiCAPcv"
_K_PART3 = b"sjbKtM9mZrbeM="

# Encrypted credentials payload (AES-CBC + HMAC via Fernet)
_ENC_BLOB = b"gAAAAABqlWmgdEcjCgIilioEACQmA37zJOdYety5w6H2Q9g1ChYcK8TFY7P3rXxExpn9wPfIWhjjszxBRdyXmmduqn38LJRe6rNUNGWgnOlTJ_TSQGNSXVQN5nldhOCHNmwy4r9rmoEt3b4dR1t2bSio00qvgiUBOctUWqjSxiGT4A1EBjRbi-VA3WMYXkvfzensXf70EGHERiOhNUaMWhetkaaVmxy8sh_iFKlGYTBERb2jxsoPst8f26R6YWvIfcePTJpuUhTOfDwlXuMMR65uRCfXu6VMDEdNdrCZaSi2P9L_Zwbr2oMccMrbY0k9sLW3CiJSZ8vJ"

def get_odoo_credentials():
    """
    Decrypts and returns the Odoo API credentials securely in memory.
    Credentials are never written to disk or shown in plain text.
    """
    try:
        combined_key = _K_PART1 + _K_PART2 + _K_PART3
        cipher = Fernet(combined_key)
        decrypted_bytes = cipher.decrypt(_ENC_BLOB)
        data = json.loads(decrypted_bytes.decode('utf-8'))
        return data['url'], data['db'], data['user'], data['pwd']
    except Exception as e:
        raise RuntimeError("Security verification failed: Unable to decode credentials.") from e

if __name__ == "__main__":
    url, db, user, pwd = get_odoo_credentials()
    print("Credentials verified successfully:", url, db, user, "Password length:", len(pwd))
