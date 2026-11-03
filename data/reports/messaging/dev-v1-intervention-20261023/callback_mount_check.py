"""Verify private UDS mount/UID only; NOT a signed operational callback or service."""
import json
import os
import socket
import stat
import struct
import subprocess
from pathlib import Path
from uuid import uuid4

import backup_verify as b

IMAGE = '5a25df47f4bb71764d2fd033f07428e5be0cbc010b33d05851a5166e89f4b175'
parent = b.PRIVATE / 'evolution-dev-v1'
os.umask(0o077)
parent.mkdir(mode=0o700, exist_ok=True)
info = parent.stat()
assert info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700 and parent.resolve() == parent
path = parent / ('check-' + uuid4().hex[:8] + '.sock')
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.settimeout(15)
owned = None
process = None
inode = None
result = {'mount_uid_check': 'NOT_RUN', 'authenticated_operational_callback': 'BLOCKED_MISSING_INDEPENDENT_IDENTITIES',
          'real_messages_sent': 0, 'database_writes': 0, 'own_processes_left': 'UNKNOWN'}
try:
    server.bind(str(path));inode = path.stat().st_ino;os.chmod(path,0o600);server.listen(1)
    js = "const net=require('net');const c=net.createConnection(process.argv[1],()=>c.write('mount-check'));c.setTimeout(5000,()=>process.exit(2));c.on('data',b=>{if(b.toString()!=='verified')process.exitCode=3;c.end();});c.on('error',()=>process.exit(4));"
    created = subprocess.run(['podman','create','--pull=never','--network=none','--memory=128m','--cpus=1',
                              '--read-only','--cap-drop=ALL','--label','team360.task=dev-v1-uds-mount-check',
                              '--volume',str(parent)+':'+str(parent)+':rw','--entrypoint=node',IMAGE,
                              '-e',js,str(path)],capture_output=True,check=True)
    owned=created.stdout.decode().strip()
    process=subprocess.Popen(['podman','start','--attach',owned],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with server.accept()[0] as peer:
        pid,uid,gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        assert uid==os.getuid()
        assert peer.recv(32)==b'mount-check'
        peer.sendall(b'verified')
    process.communicate(timeout=15)
    assert process.returncode==0
    result.update(mount_uid_check='PASS',peer_uid=uid,parent_mode='0700',socket_mode='0600',network='none',candidate_image=IMAGE)
finally:
    server.close()
    if owned:
        subprocess.run(['podman','stop','--time=5',owned],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        subprocess.run(['podman','rm',owned],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)
    if process:
        process.communicate(timeout=10)
    if inode is not None and path.exists() and path.lstat().st_ino==inode:
        path.unlink()
    result['own_processes_left']=0
    (b.OUT/'callback-mount-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
