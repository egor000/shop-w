# Browser acceptance check — ticket #1

Run `docker compose up --build -d --wait`, then open `http://localhost:8091`.

1. Stop the worker with `docker compose stop worker`. Ask “How much does the Trail Cup weigh?” Check that the question appears with “Waiting for an answer…” and another submission is disabled.
2. Refresh. The accepted question must reappear in the same conversation.
3. Start the worker with `docker compose start worker`. Observe “Preparing your answer…” followed by “Answer saved.” The answer must include `0.25 kg`, `USD 24.99`, and a “View Trail Cup” link.
4. Refresh after completion. Verify the same question and complete answer. Click “View Trail Cup” and check product facts, then return using “Back to assistant”.
5. Open the conversation URL in a separate browser profile. Alternatively, replace `localhost` with `127.0.0.1`, which uses a separate host cookie. Check “This conversation is not available in this browser.” and an empty conversation area.
6. Stop the API with `docker compose stop api`. Check that the shopper sees a connection error. Start it with `docker compose start api`, then click “Reconnect and retry”. The saved history must return and asking must become available.
7. Inspect the application at narrow and normal viewport widths. Check readable text, visible controls, and no horizontal overflow.

## Recorded verification

Chrome, Docker Desktop Linux containers on Windows, 2026-09-11/12. The live application recovered the accepted question and saved answer after refresh, process replacement during rebuilds, and an overnight reconnect. The product link opened the factual product page. A separate host cookie could not read the conversation. The API integration suite independently observes processing before completion, transport deduplication, admission validation and session separation against real PostgreSQL.

During browser verification, polling initially rebuilt the entire answer every second and interrupted a link click. Rendering now preserves unchanged history; the product link was retested successfully.

The API-stop/restart check restored history and enabled another submission. A review also identified a stale-poll race that could hide the retry control after a failed submission. The UI now ignores poll responses from an earlier interaction generation.

To reproduce that regression check, run `python tests/disrupted_proxy.py` and open `http://localhost:8092`. The fixture delays conversation GET responses for six seconds and replaces the first forwarded submission's acknowledgement with `503`. Submit while a poll is in flight. After the delayed poll returns, the retry control must remain visible. Retry must recover exactly one saved question and answer. The fixture never changes persistence or inference behavior.

This fault check passed: the retry control remained visible after the delayed poll, and retry recovered exactly one completed question and answer. The complete API suite passed (13 tests), along with strict mypy checks of all seven Python application modules. Both review axes finished with zero outstanding findings.
