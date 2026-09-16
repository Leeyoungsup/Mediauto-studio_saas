"""Download a pinned GitHub source archive without persisting credentials or forwarding them to redirects."""
import base64
import getpass
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path, authorization=None):
    headers={'Accept':'application/vnd.github+json','User-Agent':'MeDIAuto-native-installer','X-GitHub-Api-Version':'2022-11-28'}
    if authorization: headers['Authorization']=authorization
    return urllib.request.build_opener(NoRedirect()).open(urllib.request.Request('https://api.github.com'+path,headers=headers),timeout=60)


def extract(archive, destination):
    with zipfile.ZipFile(archive) as z:
        names=z.infolist()
        if sum(i.file_size for i in names) > 8*1024**3: raise ValueError('Source archive exceeds 8 GiB.')
        prefixes=set()
        for item in names:
            parts=PurePosixPath(item.filename).parts
            if not parts or '..' in parts or item.filename.startswith('/') or '\\' in item.filename or ':' in item.filename:
                raise ValueError('Invalid source archive path.')
            if stat.S_ISLNK(item.external_attr >> 16): raise ValueError('Source archive contains symlinks.')
            prefixes.add(parts[0])
        if len(prefixes)!=1: raise ValueError('Invalid GitHub archive layout.')
        for item in names:
            parts=PurePosixPath(item.filename).parts[1:]
            if not parts:continue
            dest=destination.joinpath(*parts)
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src,dest.open('wb') as out:shutil.copyfileobj(src,out)


def download(config, runtime, root):
    marker=runtime/'source.json'
    if marker.exists():
        info=json.loads(marker.read_text())
        if info['repository']!=config['repository'] or info['ref']!=config['ref']:
            raise ValueError('Source selection changed. Use a separate installation folder for another version.')
        target=root/'application'/info['commit']
        if not (target/'backend/main.py').is_file():raise ValueError('Installed source is missing; restore it before retrying.')
        return target
    username=input('GitHub username (blank for public repository): ').strip()
    authorization=None
    if username:
        if not sys.stdin.isatty():raise ValueError('Enter the GitHub token in an interactive terminal.')
        token=getpass.getpass('GitHub password field = personal access token (PAT): ')
        if not token:raise ValueError('A GitHub token is required for authenticated download.')
        authorization='Basic '+base64.b64encode((username+':'+token).encode()).decode()
        del token
    repository=config['repository'];ref=urllib.parse.quote(config['ref'],safe='')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Invalid repository name.')
    archive=runtime/'source-download.zip'
    try:
        with api(f'/repos/{repository}/commits/{ref}',authorization) as response:commit=json.load(response)['sha']
        if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Invalid commit response.')
        print('Downloading GitHub source archive...',flush=True)
        try:
            response=api(f'/repos/{repository}/zipball/{commit}',authorization)
        except urllib.error.HTTPError as e:
            if e.code not in (301,302,303,307,308):raise
            location=e.headers.get('Location','')
            parsed=urllib.parse.urlparse(location)
            if parsed.scheme!='https' or parsed.hostname!='codeload.github.com':raise ValueError('Unexpected archive redirect.')
            # The signed URL is used only in memory. Never send the Authorization header to another host.
            response=urllib.request.build_opener(NoRedirect()).open(location,timeout=120)
        with response,archive.open('wb') as out:shutil.copyfileobj(response,out)
        target=root/'application'/commit
        if target.exists():raise ValueError('Unfinished source directory exists; inspect it before retrying.')
        staging=root/'application'/('download-'+commit)
        if staging.exists():shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            extract(archive,staging)
            if not (staging/'backend/main.py').is_file():raise ValueError('This is not a MeDIAuto repository.')
            staging.rename(target)
        except Exception:
            if staging.exists():shutil.rmtree(staging)
            raise
        marker.write_text(json.dumps({'repository':repository,'ref':config['ref'],'commit':commit},indent=2))
        print('GitHub source downloaded; commit:',commit)
        return target
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'GitHub download failed (HTTP {e.code}). Check repository/ref and PAT Contents: read access.') from None
    except urllib.error.URLError:
        raise RuntimeError('GitHub connection failed. Check network access.') from None
    finally:
        authorization=None
        archive.unlink(missing_ok=True)
