class WebhookClient:
    """Extension point for outbound webhook notifications."""

    def send(self, payload: dict) -> None:
        raise NotImplementedError("Webhook delivery is not implemented yet")
