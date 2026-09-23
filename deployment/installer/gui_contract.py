"""Validation and prompt routing shared by the GUI and its privileged worker."""
import ipaddress
import re

PREFIX = 'MEDIAUTO_GUI_EVENT:'
FIELDS = ('data_root','model_path','slide_path','app_port','db_port','bind','repository','ref','username','token')

def validate(values, existing=False):
    if values.get('mode') not in ('native','docker'):
        raise ValueError('설치 방식을 선택하세요.')
    if not existing:
        if not values.get('data_root','').strip() or not values.get('model_path','').strip():
            raise ValueError('외부 데이터 폴더와 모델 폴더를 선택하세요.')
        for key in ('app_port','db_port'):
            try: number=int(values[key])
            except (KeyError,ValueError): raise ValueError('포트는 숫자로 입력하세요.')
            if not 1024<=number<=65535: raise ValueError('포트 범위는 1024~65535입니다.')
        if int(values['app_port'])==int(values['db_port']):raise ValueError('웹 포트와 DB 포트는 달라야 합니다.')
        try:ipaddress.ip_address(values['bind'])
        except ValueError:raise ValueError('올바른 웹 바인딩 IP를 입력하세요.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',values['repository']):
            raise ValueError('GitHub 저장소는 owner/repository 형식입니다.')
        if not values['ref'] or values['ref'].startswith('-'):raise ValueError('브랜치 또는 태그를 입력하세요.')
    if values.get('username') and not values.get('token'):
        raise ValueError('GitHub 사용자명을 입력했다면 PAT도 입력하세요. 공개 저장소는 둘 다 비울 수 있습니다.')
    return values

def supplied_answer(prompt, values):
    mapping=(('External data root','data_root'),('Model folder','model_path'),('Slide folder','slide_path'),
             ('Web port','app_port'),('Dedicated PostgreSQL port','db_port'),('Web bind','bind'),
             ('GitHub repository','repository'),('GitHub branch/tag','ref'),('GitHub username','username'),
             ('GitHub personal access token','token'))
    for prefix,key in mapping:
        if prompt.startswith(prefix):return values.get(key,'')
    return None

def redact(text, values):
    token=values.get('token','')
    return text.replace(token,'[REDACTED]') if token else text


def decode_log_line(raw, legacy_encodings=None):
    """Python emits UTF-8; Windows native tools may still emit the OEM/ANSI codepage."""
    if legacy_encodings is None:
        import os
        legacy_encodings = []
        if os.name == 'nt':
            import ctypes
            legacy_encodings = ['cp%d' % ctypes.windll.kernel32.GetOEMCP(),
                                'cp%d' % ctypes.windll.kernel32.GetACP()]
    for encoding in ['utf-8', *legacy_encodings]:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode('utf-8', errors='replace')
