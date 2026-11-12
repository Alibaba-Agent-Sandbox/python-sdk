"""Read-only local official SDK boundary probe; no Worker or cloud/model invocation."""
import hashlib, inspect, json, pathlib, tempfile, threading
import openai
from agent_sandbox.managed_agents import ManagedConfig, ManagedService, ManagedStore
from agent_sandbox.managed_agents.http import TokenAuthenticator, make_server

out = {'sdkVersion': openai.__version__, 'sdkModule': str(pathlib.Path(openai.__file__).name), 'operations': [], 'workerStarted': False, 'cloudCalls': 0}
with tempfile.TemporaryDirectory(prefix='abx-sdk-interop-') as tmp:
 config = ManagedConfig.from_dict({'revision':'local-probe','template':'fixture-only','models':{'fixture-model':'qwen-code'}})
 service = ManagedService(ManagedStore('sqlite:///'+tmp+'/state.db', local=True), config)
 token = 'local-only-probe-token'  # synthetic test-only loopback fixture
 auth = TokenAuthenticator({'tokens':[{'sha256':hashlib.sha256(token.encode()).hexdigest(),'owner':'local-probe','scopes':['agents:read','agents:write']}]})
 server = make_server(service, auth, port=0)
 thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
 sid = None
 try:
  for strict in (False, True):
   with openai.OpenAI(api_key=token,base_url=f'http://127.0.0.1:{server.server_port}/v1',max_retries=0,timeout=5,_strict_response_validation=strict) as client:
    ops = [('create', lambda: client.beta.agents.sessions.create(environment={'type':'self_hosted'},agent={'model':'fixture-model'},input=[{'type':'message','role':'user','content':[{'type':'input_text','text':'typed local prompt'}]}]))] if sid is None or strict else []
    ops += [('retrieve',lambda:client.beta.agents.sessions.retrieve(sid)),('list',lambda:client.beta.agents.sessions.list(limit=10))]
    for name, operation in ops:
     row={'strict':strict,'operation':name}
     try:
      value=operation(); row['decodedClass']=type(value).__name__
      body=value.model_dump(mode='json'); row['decodedFields']=sorted(body)
      if name=='create':
       sid=value.id; row['status']=value.status
      if name=='list':row['count']=len(value.data)
      if name=='retrieve':row['sameId']=value.id==sid
     except Exception as exc:
      row['errorClass']=type(exc).__name__
      if isinstance(exc,openai.APIResponseValidationError):
       row['statusCode']=exc.status_code
       cause=exc.__cause__
       if hasattr(cause,'errors'): row['validationErrors']=[{'loc':list(e['loc']),'type':e['type']} for e in cause.errors()]
      else: row['message']=str(exc)
     out['operations'].append(row)
  with service.store.transaction() as tx:
   out['acceptedTypedPrompt']=any(r.get('_prompt')=='typed local prompt' for r in tx.list('submission','local-probe'))
   out['sessionCount']=len(tx.list('session','local-probe'))
 finally:
  server.shutdown();server.server_close();thread.join(timeout=3)
print(json.dumps(out,indent=2))
