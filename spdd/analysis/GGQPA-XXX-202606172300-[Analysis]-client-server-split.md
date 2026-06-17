# SPDD Analysis: Client/Server Split for musikbox

## Original Business Requirement

> i'd like to have musikbox as a server in my home server.
> it should server as an audio file library, and i should be able to decide if i'm playing those audios on server or client devide;
> so basically, i'd like to split current app to two  - client/server - to be able to run server on my home server, and client app on my laptop/s, and later mobile/other devices.
> how would that be possible with current status quo?

Invocation: `/spdd-analysis client/server refactor`

**Derived intent:** Re-shape the existing single-process CLI into a **library host (server)** that owns the catalog, the audio files, and the heavy processing pipeline, plus one or more **thin clients** (laptop today; mobile/other devices later) that browse and control the library over a network. A first-class requirement is that the user can **choose, per listening session, whether audio is rendered on the server's own audio output or streamed to and rendered on the client device.**

---

## Domain Concept Identification

### Existing Concepts (from codebase)

- **Track / TrackId**: The catalog record (title, artist, bpm, key, genre, `file_path`, …) — the central entity; everything else references it. Today its `file_path` is a server-local absolute path, an assumption the split must break.
- **Library** (`LibraryService` over `TrackRepository` port): Query / search / inspect / import / export of the catalog — relates to Track as its aggregate query surface. This service is **pure orchestration over a port**, so it is reusable on the client unchanged if the repository becomes remote.
- **Playback** (`PlaybackService` over `Player` port): Queue management and transport control (play/pause/next/seek) — relates to Track (queue of tracks) and to the Player abstraction. Also pure orchestration over a port.
- **Player** (port; `MpvPlayer` adapter): The audio-rendering abstraction. Currently always renders on the **local** machine's audio output via libmpv, with macOS media-key / Now-Playing integration. This port is the natural pivot for the "where does sound come out" decision.
- **Catalog persistence** (`TrackRepository` / `PlaylistRepository` ports; SQLite adapters): Single-file SQLite at `~/.config/musikbox/musikbox.db`. A known DB-locking concern exists (recent commit hardening `save`).
- **Heavy processing** (`Downloader`/yt-dlp, `Analyzer`/essentia·librosa, `MetadataEnricher`/Claude, `GenreLookup`/MusicBrainz, `MetadataWriter`/mutagen): CPU- and dependency-heavy operations that act directly on files in `music_dir`. They belong wherever the files and the big dependencies live.
- **Playlist** (`Playlist` / `PlaylistRepository`): Ordered collections of Tracks — same persistence/locality concerns as the catalog.
- **Audio file** (`music_dir`, default `~/Music/musikbox`; `Track.file_path`): The physical media. The single most location-bound concept in the system.
- **Configuration** (`Config` from `~/.config/musikbox/.env`): `music_dir`, `db_path`, formats, API keys — loaded once and injected. Will need to express "am I a server or a client, and where is the server?".
- **EventBus / events** (`events/`): The TUI's in-process pub/sub (TrackStarted, ImportProgress, …). Conceptually the same shape as a network progress/notification channel.
- **App / bootstrap** (`create_app()`): The single wiring point that builds the entire object graph. Today it unconditionally builds *every* adapter (downloader, analyzer, mpv, …) in one process.

### New Concepts Required

- **Library Host (Server)**: A long-running process that owns the catalog DB, the audio files, and the heavy services, and exposes them over a network boundary. Becomes the single source of truth and the single DB writer.
- **Client (Controller / Renderer)**: A process that consumes the server's capabilities — browses the catalog, controls playback, and optionally renders audio locally. Reuses the existing services/TUI but is wired with remote port implementations and minimal local dependencies.
- **Network / API boundary (transport contract)**: The stable contract between client and server. A new concept the codebase has no equivalent for today (everything is in-process method calls).
- **Audio Stream (streamed media source)**: A network-delivered representation of a Track's bytes, seekable, so a client can render audio it does not have on its local filesystem. Generalizes "open a local file".
- **Output Target / Playback Location**: The explicit, user-selectable concept of *where audio is rendered* — server output vs client output. This is the headline new domain concept; today it is implicit and always "local".
- **Remote Repository / Remote Player (port realizations)**: New concept-level realizations of the existing `TrackRepository` and `Player` ports that satisfy the same contracts over the network rather than locally. They are how existing services stay untouched.
- **Playable Source (locator)**: A generalization of the current `file_path` notion to "something the Player can render" — a local path *or* a remote stream locator. Needed because a client renders by stream URL, not by server filesystem path.
- **Access Identity (auth token)**: A new concept governing who may reach the server — relevant the moment the boundary leaves the trusted LAN.
- **Remote Operation / Job (with progress)**: A long-running server-side action (download, analyze, enrich) initiated by a client, whose progress and outcome must travel back across the boundary — the network analogue of the existing EventBus stream.

### Key Business Rules

- **Single source of truth**: The catalog and the audio files exist authoritatively on the server; clients never assume a local copy. → governs Track, Audio file, Catalog persistence.
- **Playback location is a client-chosen property of a listening session**: The user decides server-output vs client-output, and the system must honor either without the controlling client needing the audio bytes (server mode) or the server's filesystem (client mode). → governs Output Target, Player, Audio Stream.
- **Heavy work runs where the files and dependencies are (the server)**: Download/analyze/enrich are server-side; clients trigger and observe them, they do not perform them. → governs Heavy processing, Client.
- **Clients are thin**: A client must be runnable without the heavy/native dependencies (essentia, yt-dlp, anthropic) — only what it needs to browse and (optionally) render audio. → governs Client packaging.
- **File paths are server-internal**: `Track.file_path` is meaningful only on the server; clients address media by Track identity, never by path. → governs Track, Playable Source, security of the stream surface.
- **The server is the single DB writer**: Centralizing writes on the server is both an architectural fact and a mitigation for the existing SQLite-locking concern. → governs Catalog persistence.

---

## Strategic Approach

### Solution Direction

- **Put the network boundary at the existing ports, not through the middle of the services.** The hexagonal architecture already isolates all I/O behind ports (`TrackRepository`, `Player`, `Downloader`, …). The strategic move is to realize those same ports *remotely* on the client and to *expose* the corresponding services over the network on the server. The domain core and the orchestration services (`LibraryService`, `PlaybackService`, the TUI in `cli/player/`) stay conceptually unchanged on whichever side runs them.
- **Model "where audio plays" as two realizations of the one `Player` port**, selected by the client at wiring/runtime — one that drives the server's renderer, one that renders locally from a stream. Because `PlaybackService` and the TUI depend only on the port, they remain agnostic to the choice. This is what makes the headline requirement cheap rather than invasive.
- **General data-flow direction:**
  - *Browse/manage*: client UI → remote repository realization → network → server service → catalog.
  - *Server-output playback*: client UI → remote player realization → network → server playback/renderer → server audio device.
  - *Client-output playback*: client UI → local renderer → network stream of the track → client audio device; catalog/control still flow as above.
  - *Heavy ops*: client request → server service executes on local files → progress/result streamed back.
- **Keep one codebase with a server profile and a client profile** rather than forking, leveraging the existing single `bootstrap` wiring point by splitting it into server-side and client-side assembly.

### Key Design Decisions

- **Location of the network seam — at the port boundary vs. a new bespoke RPC layer**: Trade-off — port-boundary realizations maximize reuse of existing services/TUI and keep the domain untouched, at the cost of designing remote realizations that honor the existing contracts (including state-y ones like the Player's position/duration). A bespoke RPC layer would be conceptually simpler per-call but would duplicate orchestration and bypass the architecture's main asset. → **Recommend the port boundary**; it is the highest-leverage use of the existing hexagonal design.

- **Modeling playback location — two Player realizations vs. a mode flag inside one adapter**: Trade-off — two realizations keep each one simple and keep all branching out of `PlaybackService`/TUI; a single adapter with an internal mode concentrates change but pushes conditional logic into the renderer and muddies its responsibility. → **Recommend two realizations behind the single port**, chosen at client wiring time.

- **The "playable source" generalization — keep the file-path-only player contract vs. generalize it to a location-agnostic source**: Trade-off — generalizing the one playback entry point lets the same renderer concept serve both local files (server side) and remote streams (client side), but it touches the single most central port and its existing realization, fakes, and tests. Keeping it path-only would force awkward workarounds on the client. → **Recommend generalizing the source concept**, accepting a contained, well-tested change to one port.

- **Transport style — HTTP/REST-oriented vs. binary RPC vs. custom socket protocol**: Trade-off — an HTTP-oriented boundary natively supports seekable media streaming, is directly consumable by future web/mobile clients with no extra toolchain, and yields a self-describing contract; a binary RPC is efficient but adds friction for browsers/mobile and for media streaming; a custom protocol maximizes control but maximizes work and risk. → **Recommend the HTTP/REST-oriented boundary** as the default, with a streaming-capable media endpoint.

- **Catalog persistence — keep embedded SQLite (single server writer) vs. move to a networked database**: Trade-off — at home-server scale a single embedded store with the server as sole writer is simplest and also neutralizes the known locking issue; a networked DB adds operational weight that the use case does not yet justify. → **Recommend keeping the embedded store on the server** (with concurrency hardening), revisiting only if true multi-writer needs emerge.

- **Packaging — one repository with server/client profiles vs. two repositories**: Trade-off — one repository keeps the shared domain/services in a single place and minimizes churn, at the cost of clear dependency-profile discipline so a client install does not drag in server-only heavy dependencies; two repositories give hard separation but duplicate or complicate the shared core. → **Recommend one repository with distinct dependency profiles and entry points.**

- **Access control — open on LAN vs. authenticated boundary**: Trade-off — an open boundary is fine inside a trusted home LAN and is the fastest path to value; an authenticated boundary is mandatory the moment the requirement's "mobile/other devices" implies access from outside the LAN. → **Recommend phasing**: ship LAN-first, design the contract so an access-identity concept can be added before any non-LAN exposure.

- **Long-running operation feedback — synchronous request vs. asynchronous job with a progress stream**: Trade-off — synchronous calls are trivial but break down for multi-minute downloads/analysis and tie up the client; an asynchronous job with a streamed progress channel mirrors the existing EventBus model and serves the TUI's live-update expectations. → **Recommend asynchronous jobs with a server→client progress channel** for the heavy operations.

### Alternatives Considered

- **Adopt an off-the-shelf music server (MPD/Snapcast, Plex/Jellyfin, Navidrome) instead of splitting musikbox**: Rejected — these do not carry musikbox's DJ-specific value (BPM/key/Camelot analysis, the download→analyze→enrich→tag pipeline, the custom TUI). They remain useful as **conceptual references** for the server-output and streaming models, not as replacements.
- **Network the filesystem (NFS/SMB share of `music_dir` + SQLite) and run the full app on every client**: Rejected — forces heavy/native dependencies onto every client, provides no central control point, and runs the embedded DB over a network filesystem (worsening the existing locking problem). It also gives no clean way to model server-side audio output.
- **Binary RPC transport (e.g. gRPC) as the primary boundary**: Rejected as default — adds friction for the explicitly desired browser/mobile future and complicates seekable media streaming, with efficiency gains that the home-scale use case does not need.

---

## Risk & Gap Analysis

### Requirement Ambiguities

- **No explicit acceptance criteria or first-deliverable scope**: The requirement states an end state but not what "done" means for a first usable version. ACs below are *derived* and should be confirmed.
- **"mobile/other devices" — native apps or web?**: This materially changes the priority of authentication, of an explicit contract/spec, and of audio-format compatibility (a browser cannot reliably render FLAC/opus). Needs clarification before the contract is frozen.
- **Multi-client control semantics for server-output mode**: If two clients both command the single server renderer, who wins — last command, a single "active controller", or rejection? Undefined.
- **Offline / disconnection behavior on the client**: Is any local caching expected, or is a client useless without the server? Assumed "online-only" unless stated.
- **Exposure surface**: LAN-only forever, or eventual access from outside the home network? Determines when access-identity becomes mandatory rather than optional.
- **DJ-grade playback expectations over the network**: Are gapless/low-latency/crossfade behaviors (currently tuned locally) expected to hold for client-output streaming? Network buffering trades against them.

### Edge Cases

- **`Track.file_path` is server-absolute**: A client must never interpret it locally; all client rendering must resolve media by Track identity → stream locator. Why it matters: silently treating it as local is a likely first bug.
- **Seeking during client-output playback**: Requires seekable streaming; network stalls and re-buffering must degrade gracefully. Why it matters: scrubbing is core to the DJ use case.
- **Concurrent control of the single server renderer**: Two controllers, conflicting commands. Why it matters: undefined behavior on shared output.
- **Server restart / connection drop mid-playback**: Client must detect, resync transport state, or fail cleanly. Why it matters: home servers reboot.
- **Media keys / Now Playing locality**: These only act where the renderer runs; in server-output mode the laptop's media keys do not reach the server. Why it matters: a feature that recently shipped silently stops "working" in one mode unless commands are routed.
- **Format compatibility on the rendering device**: A future web/mobile client may not decode the library's formats. Why it matters: may force a transcoding concept not in current scope.
- **Large library over the network**: Pagination/search latency that is invisible in-process becomes user-visible. Why it matters: UX of the remote browse path.
- **Long heavy operations triggered remotely**: Failures (a failed download/analyze) must surface to the initiating client, not just log on the server. Why it matters: silent server-side failure is a poor remote experience.

### Technical Risks

- **SQLite locking under networked/concurrent access** (already observed; recent `save` hardening): *Impact* — write contention/corruption risk. *Mitigation direction* — server as single writer + concurrency-friendly journaling; keep all writes server-side.
- **Change to the central `Player` port (the playable-source generalization)**: *Impact* — ripples to `PlaybackService`, the TUI, the existing mpv adapter, the fake player, and their tests. *Mitigation direction* — treat as a small, isolated, test-first contract change before any network work.
- **Correctness of seekable streaming**: *Impact* — broken scrubbing / partial playback. *Mitigation direction* — contract tests for ranged/seek behavior across the boundary.
- **Network buffering vs. responsiveness for client-output** (you already tuned buffers for Bluetooth; WiFi adds another layer): *Impact* — dropouts or laggy control. *Mitigation direction* — explicit buffering strategy and tuning, mirrored from the existing audio-buffer work.
- **`create_app()` builds everything in one process**: *Impact* — naive reuse would drag server-only heavy deps into the client. *Mitigation direction* — split assembly into server and client profiles with distinct dependency sets.
- **Testing across a process boundary**: *Impact* — loss of the current in-process testability if not designed for. *Mitigation direction* — a fake/in-memory transport and contract tests so services stay testable without a live server, consistent with the existing `Fake*` adapter pattern.
- **Security of the media/stream surface**: *Impact* — an endpoint that serves files by path invites traversal/exposure. *Mitigation direction* — address media strictly by Track identity, and gate the boundary with access identity before any non-LAN exposure.

### Acceptance Criteria Coverage

*(ACs derived from the requirement — no formal ACs were supplied; confirm before REASONS Canvas.)*

| AC# | Description | Addressable? | Gaps/Notes |
|-----|-------------|--------------|------------|
| 1 | Run a server on the home server that hosts the audio-file library (catalog + files) | Yes | Server profile + network exposure of existing services; embedded DB stays server-side. |
| 2 | Run a client app on a laptop that browses/controls the library | Yes | Remote realization of the catalog port lets `LibraryService`/TUI run client-side largely unchanged. |
| 3 | User decides per session whether audio plays on the **server** or the **client** | Yes | Two realizations of the `Player` port + a seekable stream for client output; requires the playable-source generalization. |
| 4 | Later support mobile / other devices | Partial | HTTP-oriented contract is mobile/web-friendly, but native/web client build, audio-format compatibility (possible transcoding), and access identity are out of first scope and need decisions. |
| 5 | Browse / search / manage the library from a client | Yes | Reuses existing query/search/import-export orchestration over the remote repository realization. |
| 6 | (Implied) Trigger downloads / analysis / enrichment from a client, executed server-side | Partial | Needs server-side execution plus an async job + progress channel; not part of the earliest browse-and-play slice. |
| 7 | (Implied) Multiple clients used over time | Partial | Catalog browse scales; **concurrent control of server output** is semantically undefined and must be specified. |
| 8 | (Implied) Client remains lightweight on resource-constrained devices | Yes | Distinct client dependency profile excludes essentia/yt-dlp/anthropic; confirm the local renderer's footprint per target device. |

---
