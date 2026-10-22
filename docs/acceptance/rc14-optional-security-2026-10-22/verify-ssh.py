import json,socket,threading,tempfile,shutil
from pathlib import Path
import paramiko

root=Path(tempfile.mkdtemp(prefix='rem-rc14-ssh-'))
hostkey=paramiko.RSAKey.generate(2048)
userkey=paramiko.RSAKey.generate(2048)
userkey.write_private_key_file(str(root/'key'))
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
port=listener.getsockname()[1]
(root/'known_hosts').write_text(f'[127.0.0.1]:{port} {hostkey.get_name()} {hostkey.get_base64()}\n')
done=threading.Event()
class Server(paramiko.ServerInterface):
    def check_auth_publickey(self,username,key):
        return paramiko.AUTH_SUCCESSFUL if username=='probe' and key==userkey else paramiko.AUTH_FAILED
    def get_allowed_auths(self,username):
        return 'publickey'
def serve():
    connection,_=listener.accept()
    server=paramiko.Transport(connection);server.add_server_key(hostkey)
    server.start_server(server=Server());done.wait(15);server.close()
thread=threading.Thread(target=serve,daemon=True);thread.start()
client=paramiko.SSHClient()
client.load_host_keys(str(root/'known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('127.0.0.1',port=port,username='probe',key_filename=str(root/'key'),timeout=10,auth_timeout=10,banner_timeout=10,look_for_keys=False,allow_agent=False)
assert client.get_transport().is_authenticated()
signature=paramiko.Message(userkey.sign_ssh_data(b'local security probe').asbytes()).get_text()
assert signature=='rsa-sha2-512',signature
result={'paramiko':paramiko.__version__,'loopback_ssh_key_authentication':True,'host_key_verified_with_reject_policy':True,'default_rsa_signature':signature,'nas_contacted':False}
client.close();done.set();thread.join(5);listener.close()
assert not thread.is_alive()
shutil.rmtree(root)
Path('/tmp/rem-rc14-ssh-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
