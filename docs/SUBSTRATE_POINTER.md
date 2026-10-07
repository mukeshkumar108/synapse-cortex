# Where the current architecture lives

The single source of truth for how Cortex, Companion Runtime and Honcho work together (turn path, Cortex's packets and sizes, cadence of every model call,
live conversational memory, product contract, infrastructure, history and gaps) is **`../companion-runtime/docs/SUBSTRATE.md`** (2026-10-07). It is kept
next to the Runtime because the Runtime owns the turn and the compiler. This repo keeps the product intent (`COMPANION_NORTH_STAR.md`, `COMPANION_CANON.md`)
and the data model (`CORTEX_ARCHITECTURE.md`); where those describe cadence, retrieval or consolidation, SUBSTRATE.md supersedes them.
