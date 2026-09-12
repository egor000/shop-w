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

## Worker crash recovery — ticket #2

Verified in Chrome on 2026-09-12 with the upgraded Compose deployment and existing saved conversation:

1. Stop the ordinary worker: `docker compose stop worker`.
2. Start a delayed worker: `docker compose run -d --no-deps --name shop-assistant-recovery-demo -e DETERMINISTIC_DELAY_SECONDS=30 -e WORKER_LEASE_SECONDS=2 worker`.
3. Submit “Will my Trail Cup question survive a worker crash?” and observe “Preparing your answer…”.
4. Kill that worker with `docker kill shop-assistant-recovery-demo`, then start its replacement using `docker compose start worker`.
5. The open browser changed to “Answer saved.” and displayed one complete answer to the original question, alongside unchanged earlier conversation history. Worker logs showed attempt number 2 with a new attempt ID. The recovered answer included the product link and recorded facts.

The API suite separately verifies expired ownership before reassignment, rejection of a stale answer after a replacement completes, persisted three-attempt budgets across crashes, and the actual two-minute deadline. No database state is edited to force those outcomes.

Ticket #2 validation: 22 tests passed in the complete suite, strict mypy passed for eight application modules, and both review axes have no outstanding findings. Each test uses its own PostgreSQL schema so deliberately unfinished work cannot leak into another scenario.
