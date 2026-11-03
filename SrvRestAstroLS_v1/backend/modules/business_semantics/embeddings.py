"""Async LiteLLM embedding adapter; no provider selection or fallback."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
import httpx
from modules.automation_diagnosis.litellm_client import LiteLLMClient


@dataclass(frozen=True)
class EmbeddingConfiguration:
    alias: str
    dimension: int
    revision: str

    @classmethod
    def from_env(cls):
        alias = os.getenv('TEAM360_SEMANTICS_EMBEDDING_ALIAS', '')
        revision = os.getenv('TEAM360_SEMANTICS_EMBEDDING_REVISION', '')
        dimension = int(os.getenv('TEAM360_SEMANTICS_EMBEDDING_DIMENSION', '0'))
        if not alias or not revision or dimension <= 0:
            raise ValueError('explicit_semantics_embedding_configuration_required')
        return cls(alias,dimension,revision)


def embedding_content(version):
    content = json.dumps({k: version[k] for k in ('canonical_name','definition','operational_context','aliases')},
                         ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return content,hashlib.sha256(content.encode()).hexdigest()


class LiteLLMEmbeddingAdapter:
    def __init__(self, config, *, transport=None):
        self.config,self.transport = config,transport
        self.last_usage = {}

    async def embed(self, text):
        client = LiteLLMClient(timeout_seconds=8)
        async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=8,transport=self.transport) as http:
            response = await http.post(client.base_url+'/embeddings',headers={'Authorization':'Bearer '+client.api_key},
                json={'model':self.config.alias,'input':text,'dimensions':self.config.dimension})
            response.raise_for_status()
            body=response.json()
        data=body.get('data',[])
        if len(data)!=1 or data[0].get('index')!=0:
            raise ValueError('embedding_response_contract')
        vector=data[0]['embedding']
        if (len(vector)!=self.config.dimension or any(type(x) not in (int,float) or not math.isfinite(x) for x in vector)
                or not any(vector)):
            raise ValueError('embedding_dimension_or_values_invalid')
        # Requested alias and revision must be preflighted against proxy model/info.
        self.last_usage={'usage':body.get('usage',{}),'upstream_model':body.get('model')}
        return vector
