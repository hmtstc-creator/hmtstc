# Level1 40.08 API Contract Diff

Bu rapor, frontend API çağrıları ile backend FastAPI route envanterini karşılaştırır.
Sonraki adım olan `Eksik endpoint raporu` için sınıflandırılmış fark üretir.

- Status: `ok`
- Generated at: `2026-06-14T18:59:17.963849+00:00`
- Backend route count: `897`
- Frontend call count: `94`
- Matched call count: `94`
- Missing path count: `0`
- Method mismatch count: `0`
- Critical missing count: `0`
- Runtime leaks: `0`
- Tracked runtime stores: `0`
- Unignored runtime stores: `0`
- Allowed ignored runtime stores: `2`

## Critical frontend paths

- `/api/quality/revision-37` — OK
- `/api/real/readiness` — OK
- `/health` — OK
- `/health/ops` — OK

## Top missing paths

No missing frontend paths detected.

## Top method mismatches

No method mismatches detected.

## Missing by file

No missing-path source files.

## Contract notes

- This script performs static contract review only; it does not fix endpoints.
- A review status is expected until the following missing endpoint report step classifies and resolves gaps.
- Critical frontend paths must not be missing when called: /api/real/readiness, /health, /health/ops, /api/quality/revision-37.
- /api/summary is a backend critical route, but it is not a required frontend call.
