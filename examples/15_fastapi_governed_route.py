from agentpay import governed_route, nornr_middleware


def setup(app) -> None:
    app.middleware("http")(nornr_middleware())

    @app.post("/governed")
    @governed_route(
        action_name="fastapi-governed-endpoint",
        amount=lambda *args, **kwargs: 9,
        counterparty=lambda *args, **kwargs: "openai",
        purpose=lambda *args, **kwargs: "Serve one governed endpoint call",
    )
    async def governed_endpoint(request):
        return {"ok": True, "traceId": request.state.nornr_trace_id}
