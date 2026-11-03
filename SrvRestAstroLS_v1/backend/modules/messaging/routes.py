"""Messaging-owned HTTP routes mounted once through the module registry."""
from .webhooks.evolution_whatsapp import EvolutionWhatsAppWebhookController

ROUTE_HANDLERS = (EvolutionWhatsAppWebhookController,)
