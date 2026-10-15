# Password hashing with the standard library
import hashlib
import hmac
import os
import unicodedata
from functools import cache
from dataclasses import dataclass

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_SCHEME = "scrypt"
_N , _R , _P = 2**15 , 8 , 3 # OWASP-equivalent from django.conf import settings
_SALT_BYTES = 16
_KEY_BYTES = 32


@dataclass (frozen = True)
class _Stored :
    n : int
    r : int
    p : int
    salt : bytes
    key : bytes
    
def _derive(password : str , salt : bytes , n : int , r : int , p : int) -> bytes:
    secret = unicodedata.normalize("NFKC" , password).encode("utf-8")
    
    return hashlib.scrypt(secret , salt = salt , n = n , r = r , p = p , 
                          dklen = _KEY_BYTES , maxmem = 256 * n * r)

def _parse(stored : str) -> _Stored | None:
    try : 
        scheme , n , r , p , salt , key = stored.split("$")
        if scheme != _SCHEME : return None
        return _Stored(int(n) , int(r) , int(p) , bytes.fromhex(salt) , bytes.fromhex(key))
    except ValueError : return None
    

def hash_password(password : str) -> str:
    # Return a self-describing hash string safe to store in users.password_hash
    salt = os.urandom(_SALT_BYTES)
    key = _derive(password , salt , _N , _R , _P)
    return f"{_SCHEME}${_N}${_R}${_P}${salt.hex()}${key.hex()}"

def verify_password(password : str , stored : str) -> bool:
    # True only when the password matches. Malformed input return False
    if len(password) > MAX_PASSWORD_LENGTH : return False
    
    parsed = _parse(stored)
    if parsed is None : return False
    
    key = _derive(password , parsed.salt , parsed.n , parsed.r , parsed.p)
    return hmac.compare_digest(key , parsed.key) # constant-time Compare


def needs_rehash(stored : str) -> bool:
    # True when the hash uses older parameter; re-hash after a succesful login
    parsed = _parse(stored)
    return parsed is None or (parsed.n , parsed.r , parsed.p) != (_N , _R , _P)


@cache
def _dummy_hash() -> str:
    return hash_password("timing-equalizer")

def burn_password_check(password : str) -> None:
    # Spend the tiem of a real check, for logins whose email does not exits
    verify_password(password , _dummy_hash())
