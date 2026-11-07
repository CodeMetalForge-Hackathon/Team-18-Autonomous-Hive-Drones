# Rover Lab

A local tabletop search simulator with an automatic Claude Code Opus → rover → dock → Opus loop.

## Current photographed hardware

The default `pan-sonar-light-v2` profile is based on the supplied robot photos: horizontal orange StickC, dark chassis, black wheel faces/yellow mecanum rollers, a front servo carrying one twin-transducer ultrasonic module, and an upward-facing light sensor. The model has no RGB camera, bumper switches or rescue-marker detector by default. Those remain explicit virtual options, not claims about the photographed hardware.

The front mount supports continuous sweep and move-and-hold. Nominal travel is ±45° around forward. All reach, blind-zone, beam-width, motor speed, dimensions and illumination settings are **uncalibrated assumptions**: default 80 cm reach, 2 cm blind zone, 15° beam, 90°/s head slew, 5 pings/s. Adjust them after measuring the real assembly. Two transducers provide one range channel, not left/right distances.

Use **Inspect robot** for a close view. **Scan in place** sweeps the head without driving. Manual head controls switch to Manual mode; Run or single-tick advances the servo. A top-light readout falls under shelter roofs. Dark ambient lighting can produce the same reading, so light is evidence, not an oracle hidden flag.

Old experiments retain `legacy-three-ray-v1`. Their replays use frozen v1 physics and the older visual assembly. They cannot continue as new physical-profile experiments: start a fresh run so Opus does not inherit observations from nonexistent sensors. Reference photos and their metadata remain local and are not bundled in the repository.

## Minimal mission supervisor

Open http://localhost:8765/supervisor.html, or use the **Mission supervisor** section at the bottom of the simulator. It is a single-screen operator view: agent map, operational state, and one caption at a time. Captions are labeled LEARNED, PLAN, or ROM CHANGE and are limited to 72 characters / 12 words, displayed in at most two lines. Pause/fullscreen are the only view controls. Opus writes these captions in `supervisor.json`; the engineering debrief stays separate. Old recordings without compact reports show explicitly marked excerpts.

The supervisor API returns only published beliefs, compact reports and the last **returned odometry estimate**. It excludes the true world, live true pose and hidden objective totals. Missing timestamps/low confidence are shown as uncertain; older points fade, revisions are highlighted, and removed estimates briefly remain as dashed ghosts. No map is treated as permanent truth.

At the dock, the engineering view can edit and apply the current table to the next sortie. Keep the dock fixed. Physical-world edits are recorded only in trusted observer state, never as a hint in Opus's inbox. Opus must detect changes in subsequent sensor logs, reconcile contradictory evidence, revise its map, and adapt the plan/ROM. Changes during a deployed sortie are rejected; each deployment records the actual world version it used for faithful replay.

## Launch

In Linux, macOS, or WSL, from the repository root:

```bash
cd simulator
python3 server.py
```

Open http://localhost:8765. On Windows, `start.cmd` launches the same server in the default WSL distribution from the checkout directory. Keep the terminal open. A Python static file server still runs the manual simulator but cannot invoke Claude or manage experiments.

Dependencies: Python 3.10+, Node.js 18+, and the authenticated `claude` CLI with `--restricted` support (tested with Claude Code 2.1.319). The server detects Node on PATH, including `node.exe` through WSL interop. Set `ROVER_NODE` to its executable path if automatic detection fails. Existing Claude Code login is reused; there is no OpenAI API dependency. Run `claude auth login` in the same environment as the server if login is unavailable. Linux/WSL has been tested; the Windows launcher requires WSL. The UI uses locally vendored Three.js 0.170.0, local STL assets, and system fonts; rendering needs no CDN or font service.

## Automatic experiment

1. Edit the desk, dock position, and hardware settings before starting. The start marker is the physical download/recharge dock.
2. Set the maximum number of sorties and simulation speed in **Opus / Dock & Carry**. Click **Start Opus experiment**. Each click creates a new experiment with a new empty agent map.
3. Opus receives only a hardware contract, a mission objective, empty map/notes, and the ROM/file protocol. It receives no true map, table dimensions, object list, world coordinates, or hidden target total.
4. The harness invokes the real `claude -p --model opus` process. Opus writes `controller.rom`, `mission.json`, `map.json`, and `notes.md`. Local validation checks its ROM and plan. Invalid output is returned as local validation feedback, with up to three attempts and no additional environmental evidence.
5. The harness freezes that ROM and deploys the rover. Claude is not running and receives no live telemetry while the rover is away. The trusted simulator runs independently of the browser, so closing the browser does not stop a sortie.
6. The rover must actually leave the dock vicinity (>10 cm), then return within 6 cm of its center. A physical-contact surrogate closes the connection. Only then is a new sensor log written to the agent's observations directory. Docking also recharges and restores the departure pose for the next outing.
7. The next Claude turn starts automatically with the same workspace, new inbox, and delivered observations. Conversations are fresh; persistent memory is in the agent's files. The agent updates its map, notes and next controller.
8. The loop stops when Opus explicitly finishes, the sortie limit is reached (after a final review-only dock analysis), the rover becomes stranded, a CLI/runtime error occurs, or the human clicks **Stop**. A failed return never uploads that outing's data. There is no privileged return controller, retrieval or mid-sortie code update.

The sortie time limit is a failure deadline, not an automatic return. This setup tests whether the agent can build controllers that gather useful evidence and come home; it does not guarantee rescue success. Calls use the existing Claude subscription/API configuration. The CLI's resolved model identifier appears in the workspace panel. Each planning process has a ten-minute watchdog; deployments are limited to 180 simulated seconds each.

## Watching the experiment

The main 3D view is **human-only ground truth**. The right-hand map is **Opus's own `map.json`**, initially unknown. It is rendered in dock-relative coordinates; it is never filled from simulator geometry. Amber points are estimated occupied space, green points free space, and labeled points agent-defined landmarks.

The **Files** tab shows current workspace files, including new observations and ROM updates, polled live. The **Transcript** tab shows emitted assistant text, tool calls/results, concise decisions, validation messages and harness events. Private thinking blocks are deliberately omitted; this is not a display of internal chain-of-thought. The history lists completed planning decisions.

The human can orbit and zoom the true world while Opus works. Manual editing and ROM controls are disabled during automatic experiments. After the experiment ends, **Reset** returns to manual simulation. A server restart restores the last persisted observer state and workspace for inspection; it does not resume a partially completed deployment or recover undocked observations. **Continue from dock** can extend an existing experiment when the rover is physically docked, preserving the workspace, map and returned logs. It is unavailable for stranded rovers. Use **Start Opus experiment** for a fresh experiment instead.

## Information boundary

Agent workspaces are created outside the simulator project:

```text
~/rover-opus-workspaces/<run-id>/agent/
  hardware.json
  inbox.json
  controller.rom
  mission.json
  map.json
  notes.md
  observations/sortie-001.json
  ...
```

The agent runs with Claude Code `--restricted`, `--safe-mode`, an empty MCP configuration, no project/user settings, disabled skills, and only Read/Write/Edit/Glob/Grep tools. Restricted mode confines ordinary file access to its working directory; Claude Code can also read its own generated tool-result artifacts when large outputs are spilled into its session storage. Those artifacts originate from the same allowed workspace data. No shell, browser, web search, custom plugins, simulator API, simulator source or trusted observer state is exposed to the agent. A real CLI isolation probe verified an attempted parent-directory read was denied while an in-workspace write succeeded.

Hardware, inbox and existing observation files are hash-checked after each planning turn; modifying them blocks deployment. A bounded analysis helper responds to `analysis-request.json` during dock planning. It can evaluate numeric expressions or project already-delivered range readings using logged noisy odometry; it never imports the simulator or reads observer state. Its result is placed in `analysis-result.json`. Opus must decide how to merge that evidence into its map. This supplies calculation ability without enabling a shell or giving the agent hidden geometry. The complete system prompt is in `opus-contract.txt`. Trusted execution snapshots, versioned ROM/map/notes files, and sanitized transcripts are saved separately in `.runs/<run-id>/`. These trusted files are not agent input. `.runs/` is ignored by Git and not served as static content.

This is an experimental tool-access boundary using Claude Code's restricted mode, not an OS-level security sandbox against a malicious CLI executable. The CLI itself retains the network access needed to call its provider.

## Rover observation and ROM contract

The controller is a small assembly VM, not native ESP32 firmware. Register RAM is configurable, with one float32 per register. Up to 1024 instructions are allowed. Every 100 ms tick executes at most the configured instruction budget, ending early at `yield`. Execution resumes at the next instruction on the next tick. Movement commands persist until overwritten. Labels and arguments are validated. User ROMs are interpreted and never evaluated as JavaScript.

Instructions: `sense`, `set`, `add`, `sub`, `mul`, `div`, `lt`, `gt`, `abs`, `sqrt`, `sin`, `cos`, `atan2`, `wrap`, `rand`, `jz`, `jnz`, `jmp`, `move`, `strafe`, `turn`, `yield`. Angle math is in degrees; turn is clockwise. Division by zero and non-finite register results become zero. The interface and system prompt document syntax.

Sensors exposed to the ROM and carried in returned logs:

- `range`, `range_valid`: one sampled ultrasonic cone; invalid/no-echo reports `-1`, not maximum clearance. The physical profile has no fixed front/left/right channels.
- `pan`, `pan_ready`: estimated head angle and whether a hold target has been reached. There is no independent servo encoder measurement.
- `range_angle`, `range_time`, `range_age`, `range_seq`: the angle/time/identity of the latest ping. The module continues sampling while sweeping. Old pings are not new observations.
- `range_x`, `range_y`, `range_yaw`: estimated sensor origin and chassis heading at that ping, derived from commanded odometry and mount offsets. Logs/projected maps never use the true pose. The pose is frozen with the sample even when the rover/head subsequently moves.
- `light`: normalized 0..1 upward illumination, with configurable noise, ambient level and roof leakage. This is not lux or a concealment flag.
- `odom_x`, `odom_y`, `yaw`: noisy, command-integrated dock-relative estimates. Collisions can accumulate error; these are not encoders or a compass.
- `dock`, `time`, `battery`: local dock surrogate, elapsed time and synthetic energy.
- `target`, `bearing`, `observer`, `bumper`, `rescued`: virtual extras, only useful when their explicitly enabled hardware/game option exists; otherwise zero. No hidden rescue total is given to Opus.

Commands `pan DEG` cancel sweeping, slew toward a logical angle and hold. `sweep DEG_PER_SECOND` oscillates at a signed initial direction, reversing at travel limits; repeating the same command preserves phase. `sweep 0` holds the current angle. Translation can continue while the head moves.

The ultrasonic model samples five rays within its beam and returns the nearest reflector, so projecting an endpoint along the centerline has angular uncertainty. It samples from the front-mounted transducer, not the chassis center. No echo is unknown and is excluded from free-space projection. The horizontal sensor does not see tabletop drop-offs or laptop bases below its modeled 2.4 cm height; raised laptop screens can reflect it. Collision footprints remain solid, so an apparently clear beam can still miss a low obstruction. The simulated edge guard prevents falls without inventing a sensor echo.

The logger samples at 5 Hz into a 64 KiB flash ring, separate from controller register RAM. Long outings overwrite oldest rows. Returned logs contain timestamps, readings, commands, and logger statistics, never true poses or geometry. The flash limit counts serialized sample payloads; transport metadata/JSON formatting are not included. The random seed makes identical runs repeatable. Different ROM random usage can change later range-noise samples; odometry uses its own seeded stream.

## Table and physics

The default desk is 250 × 100 cm, with three 32 × 23 cm laptops, four Ø7 cm bottles, and two 34 × 28 cm shelters. Cardboard shelters have three 1 cm walls and a 15 cm-high roof; their left faces are open and interiors are traversable. Bottles have circular collision footprints; laptops have rectangular footprints. The table boundary stops movement instead of simulating falls.

Motion uses a conservative 7.5 cm circular robot radius in the photo profile (8.5 cm in legacy archives) and ideal holonomic kinematics on a flat surface. Swept moves advance in at most 0.5 cm increments, preventing tunneling through thin walls. The official robot CAD is converted from millimetres to centimetres for 1:1 display. Shell/casing/gripper assembly transforms are approximate; wheels, chassis, servo and display are procedural approximations. Asset provenance is in `assets/sources.json`; Three.js licensing is in `vendor/THREE-LICENSE.txt`.

The world is visually 3D, with planar navigation. The sonar ignores low laptop bases and overhead roofs and samples raised screens/walls/bottles at its approximate height. Virtual camera occlusion remains planar; even transparent bottles conservatively occlude markers. Shelter roofs are overhead cover, not ground obstacles. There is no independent observer line-of-sight hiding score, climbing, falling, rigid-body physics, wheel slip, real camera image processing, gripper dynamics, or processor cycle-accurate emulation. Do not use the model to verify real-world clearances.

When the optional virtual rescue detector is enabled, markers are confirmed within 10 cm with clear sight, independent of the optional virtual camera; this is a modeled close-range detector. Normal manual missions stop after all markers are confirmed. Automatic Opus sorties continue so the rover can return, without revealing a hidden success total.

Energy is a synthetic experiment budget: `dt × (1 + 0.4 × translation_fraction + 0.15 × abs(turn_command))`. It is not an electrical battery model.

## Manual experiments

Use the arena tools to place objects, draw obstacles, move the dock or add markers. Right-click erases an object and its collision parts. **Restore tabletop scene** restores the preset. Tools switch to the 2D editor; **3D rover**, **Follow rover**, and **Arena overview** switch back. Export/import preserves arena, hardware and manual ROM as JSON. Browser edits otherwise live only in memory.

Manual controls are W/S forward/back, A/D strafe, Q/E rotate while the mission runs. Built-in comparisons run the three baselines on five matching seeds, stopping at completion, energy exhaustion or 600 simulated seconds; they do not invoke Opus or include the current custom ROM. Current baselines are Scan in place, Guarded forward probe, and Seek low light. They are deliberately limited examples, not guaranteed solvers.

## Checks and files

```bash
node --test test.mjs
python3 -m unittest -v test_http.py test_harness.py test_replay.py test_supervisor.py
```

Core checks cover ROM validation, repeatability, occlusion, contact, rescue, bounded execution, battery, tabletop geometry, enterable shelters and edge/thin-wall stopping. Harness tests use real simulation workers but no model calls: successful physical upload, no-departure/stranded data withholding, bounded flash, two automatic sorties with delivery before replanning, local validation, and bounded derived-data analysis. A real Opus smoke experiment additionally exercises the CLI, firmware edits, successful dock return, and automatic next invocation. Browser checks cover both views, workspace/transcript controls and responsive layout.

`engine.mjs`: simulation + VM. `sortie.mjs`: trusted headless rover worker. `server.py`: local server and dock/CLI orchestration. `opus-contract.txt`: agent system prompt. `dock_data.py`: bounded delivered-data arithmetic/projection helper. `mission-client.mjs`: observer/workspace UI. `view3d.mjs`: 3D rendering. `app.mjs`: manual simulation/editor. `validate.mjs`: bounded ROM/start validator.

## Sortie replay and debrief

Use **Sortie replay** above the 3D scene to choose an experiment and a completed sortie, then **Load replay**. Play/pause, scrub the timeline, or change playback speed. **Back to live** restores the current rover and belief map. Live planning/deployments continue independently throughout playback; replay never invokes Claude, deploys a ROM, delivers observations, or modifies the workspace.

The debrief shows departure intent, elapsed time, contact ticks, newly confirmed targets, delivered samples, Opus's archived post-return knowledge/notes, map counts before and after analysis, and the next-round plan. Post-sortie analysis is the snapshot from planning turn N+1, not the pre-departure snapshot from turn N. If it is still running or the experiment stopped at its sortie cap, the panel says analysis/next plan are pending rather than inventing a summary. Stranded outings deliver no new knowledge. Before/after knowledge selection changes the belief map to the corresponding archived version; workspace files and transcripts remain live.

Each sortie includes a colored unified ROM diff against the preceding sortie in the same experiment, plus the complete deployed ROM. The first controller is compared against an explicitly empty baseline. The next plan is shown separately, as Opus wrote it.

New sorties record a human-only frame on every simulation tick. Older sorties are reconstructed using their saved ROM, world, seed and hardware settings, without any model calls. Their final state, saved trajectory and uploaded log must match the original record before replay is shown. If the current simulator cannot reproduce the record, playback is withheld with an explanation. These observer traces never enter the agent workspace and do not count toward the rover logger's 64 KiB flash limit.

`server.py` serves replay directly on port 8765. `history_server.py` is an optional read-only sidecar on port 8766 for legacy servers; normal launches do not require it.

Replay verification: `python3 -m unittest -v test_replay.py`. Checks cover recorded playback, verified legacy reconstruction, mismatched reconstruction refusal, ROM diffs, correct before/after analysis alignment, pending plans, read-only access and invalid experiment paths.

## Continuous experiment replay

Click **Replay whole experiment** to watch sortie 1 → dock analysis → sortie 2 → dock analysis, through the complete archived run. Playback advances automatically. Use the chapter buttons or **Next chapter** to jump; **Pause at each dock arrival** lets you stop and inspect before resuming. The timeline slider controls the current flight or analysis chapter. Dock activity is compressed for playback rather than reproducing minutes of idle model processing.

During a flight, the belief map and knowledge cards show what Opus knew at departure. At the dock, replay shows its emitted explanations, file-tool activity, range-analysis calls, published map revisions, and controller edits. The final debrief includes findings, uncertainties, the next plan, and specific ROM changes with their reasons. The actual next-ROM unified diff appears alongside the ROM diff used for the outgoing sortie. Private thinking blocks are never included.

Future planning turns capture published map/notes/ROM/debrief snapshots in trusted `updates-NNN.jsonl` files, outside the agent workspace. Older rounds use recoverable published Write events and their final archived map, explicitly labeled as legacy capture; missing intermediate edits are not fabricated. Workspace files and the ordinary live transcript remain live while the continuous replay controls the historical map and dock activity panel.

Opus now must write `debrief.json` after each return, with observed_sortie, learned, uncertainties, next_plan, rom_changes (change/why pairs), and evidence. The harness validates and archives it with the controller and map. Even at a sortie cap, a final review-only Opus turn analyzes the last upload and prepares a debrief/next ROM without deploying another outing. **Review last return** runs that analysis separately for an already docked experiment. The sortie cap counts deployments, not this final analysis call.

Continuing from dock retains all previous observations and starts at the next deployment number. A prepared review-only plan is not counted as a flown sortie. Historical records lacking structured debriefs keep their original published summaries; the viewer labels the missing structured fields instead of attributing a new summary to the past agent.

## Public repository and local data

Only simulator source, tests, prompts, documentation and licensed assets are included. Experiment archives, Claude transcripts, credentials and agent workspaces are deliberately excluded. A fresh checkout has no previous replay history; start an experiment to create local recordings. The original local experiment files are not part of this repository.

Keep `.runs/`, `~/rover-opus-workspaces/`, `.claude/`, `.env` files, authentication state and flash backups out of commits. Logs and saved sessions can contain file paths, account metadata, prompts and tool output even when private thinking blocks are omitted. Review any exported recordings separately before sharing. No API key or login token belongs in source code or a launch script.

Run `server.py` locally. It invokes an authenticated Claude CLI and can start paid/subscription-backed model calls through its control endpoints. It binds only to `127.0.0.1`, accepts only localhost/loopback Host headers, and rejects cross-origin control requests; do not expose it through public hosting, tunnels or port forwarding without adding authentication and reviewing the API. Publishing source is separate from running the control server as a public service.

This simulator does not send movement commands to physical hardware. Its ROM VM, geometry and sensors are approximations, and it does not validate real rescue performance or physical pickup. The repository's hardware firmware remains a separate component.

New simulator code follows the repository's Apache-2.0 license. Bundled M5Stack STL models and Three.js retain their MIT notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Revisable beliefs and compact reports

New Opus turns must produce `supervisor.json` with exactly three short categorized reports, linked to the latest delivered sortie. The harness validates text length/category/observation identity before archiving. It also validates map revisions, per-point confidence, last-seen sortie and uncertainty status; changed point beliefs require an increased revision. The detailed `debrief.json` remains available for evidence and engineering review.

The contract requires map revision numbers, per-point confidence, last-seen sortie, observed/uncertain/revised status, and evidence-linked changes. A missing echo alone is not evidence that an object moved. Opus must compare fresh measurements, pose uncertainty and beam width, then explicitly distinguish a revised estimate, environmental movement, and unresolved conflict. Updated beliefs must affect both the next plan and controller where appropriate.

`supervisor.py` produces the restricted operator projection, `supervisor.html`/`.mjs`/`.css` render it, and `test_supervisor.py` checks brief limits, information separation and environmental changes without model hints. `robot-physical.mjs` builds the photo-informed mesh; `legacy/` preserves the old simulator/contract for historic replays.

The ideal motion model is not a calibration of the physical robot. See the repository's [physical calibration observations](../docs/physical-calibration.md), where measured lateral/rotational coupling is being investigated separately. External-camera truth is not fed into the simulator agent or the supervisor's belief view.
