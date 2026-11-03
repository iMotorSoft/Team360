"""Explicit isolated callback app factory. Never mounted by Srv01/Srv05 implicitly."""
from litestar import Litestar, Request, post
from litestar.exceptions import NotAuthorizedException


def create_transport_app(pool, receivers):
    # receivers is a trusted historical binding registry, not a caller-selected URL.
    @post('/transport/v1/callbacks/{binding_id:str}', status_code=200)
    async def callback(binding_id: str, request: Request) -> dict:
        try:
            if int(request.headers.get('content-length', '0')) > 65536:
                raise ValueError('Body too large')
            raw = await request.body()
            if len(raw) > 65536:
                raise ValueError('Body too large')
            receiver = receivers[binding_id]
            outcome = await receiver.receive(pool, await request.json())
            return {'status':outcome}
        except Exception:
            raise NotAuthorizedException('Transport callback denied') from None
    return Litestar(route_handlers=[callback], debug=False)
