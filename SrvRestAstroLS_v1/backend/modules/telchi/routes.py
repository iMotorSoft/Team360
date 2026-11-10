"""Telchi-owned HTTP routes; no alternate identity or research implementation."""
import asyncio
import json
import os
import time
from uuid import UUID

from litestar import get, post, Request
from litestar.exceptions import HTTPException
from litestar.response import ServerSentEvent

from modules.console.auth import extract_bearer_token, verify_console_access_token, ConsoleAuthError
from .console_http import get_runtime
from .exploratory_sql.validator import Rejected


def runtime_for(request):
    if (os.environ.get('TEAM360_ENV') not in {'dev', 'development'}
            or os.environ.get('TEAM360_TELCHI_CONSOLE_ENABLED') != '1'):
        raise HTTPException(status_code=404)
    try:
        return get_runtime(request)
    except Exception:
        raise HTTPException(status_code=503, detail='Luna no está configurada en este servidor.') from None


async def authorize(request, runtime):
    service = runtime.service
    try:
        token = extract_bearer_token(request.headers.get('Authorization'))
        principal = verify_console_access_token(token, public_keys_by_id=service.keys,
            issuer=service.issuer, leeway_seconds=0)
        # The experimental UUID bootstrap is NOT an enterprise login.
        if principal.claims.get('amr') != ['pwd'] or 'workspace_id' not in principal.claims:
            raise ConsoleAuthError('password_session_required')
    except ConsoleAuthError:
        raise HTTPException(status_code=401, detail='Iniciá una sesión real de Console.') from None
    try:
        scope = await service.resolve(token)
    except Rejected:
        raise HTTPException(status_code=403, detail='Sesión o ámbito empresarial no autorizado.') from None
    permitted = any(p.organization == scope.organization and p.workspace == scope.workspace
        and p.whole_dataset and p.permission in scope.permissions for p in service.policies)
    if not permitted:
        raise HTTPException(status_code=403, detail='No tenés permisos para consultar estas fuentes.')
    return token, scope


@get(['/api/telchiai/session', '/api/telchi/luna/session'])
async def luna_session(request: Request) -> dict:
    runtime = runtime_for(request)
    _, scope = await authorize(request, runtime)
    return dict(user_id=scope.user_id, organization=scope.organization, workspace=scope.workspace)


@post(['/api/telchiai/ask', '/api/telchi/luna/ask'], status_code=200)
async def luna_ask(request: Request, data: dict) -> ServerSentEvent:
    runtime = runtime_for(request)
    token, _ = await authorize(request, runtime)
    try:
        if set(data) != {'question', 'conversation_id'}:
            raise ValueError()
        question = data['question']
        if not isinstance(question, str) or not question.strip() or len(question.encode()) > 6000:
            raise ValueError()
        conversation_id = str(UUID(data['conversation_id']))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(status_code=400, detail='Consulta o conversación inválida.') from None

    async def events():
        started = time.monotonic()
        queue = asyncio.Queue(maxsize=64)
        loop = asyncio.get_running_loop()
        def progress(message):
            def enqueue():
                if not queue.full():
                    queue.put_nowait(str(message)[:240])
            loop.call_soon_threadsafe(enqueue)
        task = asyncio.create_task(runtime.service.ask(token, question, runtime.evidence_sink(),
            progress=progress, conversation_id=conversation_id))
        def event(kind, value):
            return {'event': kind, 'data': json.dumps(value, ensure_ascii=False)}
        try:
            yield event('accepted', {'conversation_id': conversation_id})
            while not task.done():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1)
                    yield event('progress', {'message': message})
                except asyncio.TimeoutError:
                    # Transport heartbeat, not an invented research step.
                    yield {'comment': 'keep-alive'}
            report = await task
            # Only presentation-safe fields; model prose, SQL, paths and evidence
            # handles are private. The bridge reauthorizes before this return.
            yield event('result', {key: report.get(key) for key in (
                'status', 'business_answer', 'clarification', 'publication', 'snapshot',
                'question_coverage')} | {'elapsed_seconds': round(time.monotonic() - started, 2)})
        except Exception:
            yield event('error', {'message': 'La investigación no pudo completarse. Conservamos los mensajes; verificá tu sesión y reintentá.',
                'elapsed_seconds': round(time.monotonic() - started, 2)})
        finally:
            if not task.done():
                task.cancel()
            # The existing bridge cancels SQL and joins its worker on disconnect.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()

    return ServerSentEvent(events(), headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


ROUTE_HANDLERS = (luna_session, luna_ask)
