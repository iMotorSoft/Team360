"""Text controls until native interactive Evolution messages are accredited."""
from modules.messaging.delivery_guard import META_TEXT_LIMIT, guard_outbound

OPTIONS = '\n\n¿Querés continuar con esta consulta o iniciar una nueva?\nContinuar — Nueva consulta'


def with_options(text):
    if text.endswith(OPTIONS):
        return text
    return guard_outbound(text, limit=META_TEXT_LIMIT - len(OPTIONS)).text + OPTIONS
