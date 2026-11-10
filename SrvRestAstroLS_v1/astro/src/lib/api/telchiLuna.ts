// TelchiAI uses the same-origin DEV proxy, independently of the central REST server.

export type LunaResult = {
  status: string;
  business_answer?: string;
  clarification?: string;
  publication?: string;
  snapshot?: string;
  question_coverage?: string;
  elapsed_seconds: number;
};

async function checked(response: Response) {
  if (!response.ok) {
    if (response.status === 401) throw new Error('La sesión venció o no es válida. Cargá una sesión real de Console.');
    if (response.status === 403) throw new Error('Acceso rechazado: la sesión no tiene autorización para estas fuentes.');
    throw new Error(`Luna no está disponible (${response.status}). Tus mensajes permanecen en esta página.`);
  }
  return response;
}

export async function verifyLunaSession(token: string) {
  const response = await checked(await fetch('/api/telchiai/session', {
    headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
  }));
  return response.json() as Promise<{ user_id: string; organization: string; workspace: string }>;
}

export async function askLuna(token: string, question: string, conversationId: string,
  signal: AbortSignal, progress: (message: string) => void): Promise<LunaResult> {
  const response = await checked(await fetch('/api/telchiai/ask', {
    method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, conversation_id: conversationId }), signal, cache: 'no-store',
  }));
  if (!response.body) throw new Error('El servidor no abrió el stream de Luna.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: LunaResult | undefined;
  try {
    while (true) {
      const chunk = await reader.read();
      buffer = (buffer + decoder.decode(chunk.value, { stream: !chunk.done })).replace(/\r\n/g, '\n');
      if (buffer.length > 1024 * 1024) throw new Error('La respuesta superó el límite de transporte.');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = frame.split('\n');
        const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
        const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
        if (!data) continue;
        const value = JSON.parse(data);
        if (event === 'progress') progress(value.message);
        if (event === 'error') throw new Error(value.message);
        if (event === 'result') result = value;
      }
      if (chunk.done) break;
    }
    if (!result) throw new Error('Se interrumpió la conexión. No recibimos una respuesta final; tus mensajes se conservan.');
    return result;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
