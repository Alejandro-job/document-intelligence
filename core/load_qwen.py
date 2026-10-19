"""Cargar el modelo solicitado, reutilizando memoria y caché antes de descargar."""
import importlib.util,os,subprocess,sys,time

REPO='Qwen/Qwen2.5-1.5B-Instruct'

def cargar(espacio,permitir_descarga=True):
 faltan=[p for p in ('torch','transformers','safetensors','lmformatenforcer') if importlib.util.find_spec(p) is None]
 if faltan:
  paquetes={'torch':'torch>=2.4,<3','transformers':'transformers>=4.45,<6','safetensors':'safetensors','lmformatenforcer':'lm-format-enforcer>=0.11,<1'}
  print('Instalando bibliotecas faltantes:',', '.join(faltan),flush=True)
  subprocess.run([sys.executable,'-m','pip','install','-q',*[paquetes[p] for p in faltan]],check=True)
 import torch,transformers
 from transformers import AutoModelForCausalLM,AutoTokenizer
 inicio=time.monotonic();m=t=None;origen=''
 for ma,ta in [('modelo_qwen','tokenizer_qwen'),('modelo_ia','tokenizer_ia'),('modelo_qwen','tokenizador_qwen')]:
  if espacio.get(ma) is not None:
   candidato=espacio[ma]
   if getattr(getattr(candidato,'config',None),'model_type','')!='qwen2':continue
   m=candidato;t=espacio.get(ta);origen='modelo_en_memoria';break
 if m is None:
  version=tuple(int(v) for v in transformers.__version__.split('.')[:2])
  dtype=torch.float16 if torch.cuda.is_available() else torch.float32
  kw={'trust_remote_code':False,'use_safetensors':True,
      ('dtype' if version>=(4,56) else 'torch_dtype'):dtype}
  if version<(5,0):
   if importlib.util.find_spec('accelerate') is None:
    subprocess.run([sys.executable,'-m','pip','install','-q','accelerate>=0.26,<2'],check=True)
   kw['low_cpu_mem_usage']=True
  try:
   t=AutoTokenizer.from_pretrained(REPO,local_files_only=True,trust_remote_code=False)
   m=AutoModelForCausalLM.from_pretrained(REPO,local_files_only=True,**kw);origen='cache_local'
  except OSError:
   if not permitir_descarga:raise RuntimeError('Qwen no está completo en caché y la descarga está deshabilitada')
   print('Descargando Qwen desde su repositorio oficial. Esta descarga se conserva en la caché de Colab.',flush=True)
   t=AutoTokenizer.from_pretrained(REPO,trust_remote_code=False)
   m=AutoModelForCausalLM.from_pretrained(REPO,**kw);origen='repositorio_oficial'
  if torch.cuda.is_available():m=m.to('cuda')
 if t is None:
  repo=getattr(m.config,'_name_or_path',None) or REPO
  try:t=AutoTokenizer.from_pretrained(repo,local_files_only=True,trust_remote_code=False)
  except OSError:
   if not permitir_descarga:raise RuntimeError('Falta el tokenizador correspondiente al modelo')
   t=AutoTokenizer.from_pretrained(repo,trust_remote_code=False)
 if not getattr(t,'chat_template',None):raise ValueError('El tokenizador no contiene la plantilla del modelo')
 if max(t.get_vocab().values())>=m.get_input_embeddings().num_embeddings:raise ValueError('Modelo y tokenizador incompatibles')
 if next(m.parameters()).device.type=='cpu':torch.set_num_threads(min(4,max(1,os.cpu_count() or 1)))
 espacio['modelo_qwen']=m;espacio['tokenizer_qwen']=t
 info={'modelo':getattr(m.config,'_name_or_path',REPO),'commit_modelo':getattr(m.config,'_commit_hash',None),
  'origen':origen,'torch':torch.__version__,'transformers':transformers.__version__,
  'dispositivo':str(next(m.parameters()).device),'dtype':str(next(m.parameters()).dtype),
  'segundos_carga':round(time.monotonic()-inicio,3),'entrenamiento':False}
 from importlib.metadata import version as version_paquete
 info['lm_format_enforcer']=version_paquete('lm-format-enforcer')
 print('MODELO LISTO:',info['modelo'],'|',info['dispositivo'],'|',origen,flush=True)
 return m,t,info
