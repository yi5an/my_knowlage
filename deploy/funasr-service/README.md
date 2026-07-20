# FunASR service

`server.py` is the OpenAI-compatible ASR service used by KnowPilot's
production `knowpilot-asr-nano` container. The production container mounts it
at `/app/server.py`.

When updating the service, deploy this tracked file to
`/home/yi5an/asr-nano/server.py` on the server, then restart
`knowpilot-asr-nano`. An ASR result with no detected speech is a valid response
and must return HTTP 200 with an empty `text` field so the backend can continue
with later audio windows.
