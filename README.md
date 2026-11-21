# Linux Pressure Stall Information (PSI) Status App
`psistat` is a python3 program to display PSI values and to capture/display exception events. See [PSI - Pressure Stall Information — The Linux Kernel documentation](https://docs.kernel.org/accounting/psi.html) for more information.

## The Unique Value of `psistat`

`psistat` fills a critical gap in Linux monitoring by providing one simple package that offers:

* **High-Granularity, Calculated Averages:** It provides **1s, 3s, and 10s averages** — data points that are more relevant for real-time latency debugging than the kernel's $60s$/$300s$ averages.
* **Smart Event Logging:** It automatically logs incidents that cross user-defined thresholds ($1\%$–$99\%$) on the average for the interval you choose (`i`, default 10s), with a **cooldown** of one event per stat per interval, and provides forensic data (sequence number, absolute time, interval used).
* **TUI and Dump Capability:** Instantly **dump the historical log** (last 1000 events; 200 shown on screen unless `b` is on) for copy/paste — a major convenience for quick troubleshooting and reporting.
* **Simplicity:** It's a Python application installed via `pipx`—easy to install, easy to run, and requires zero configuration.

While the raw PSI data exists in the kernel, `psistat` combines live TUI monitoring, high-resolution calculation, and event logging in one small tool.

---

## Interpreting PSI Values

PSI percentages represent the fraction of time that some or all tasks were stalled waiting for a resource. Since PSI percentages are workload-dependent, there is no single "bad" value, but these are general guidelines:

* **`full` Stalls (Critical):** Any sustained $\mathbf{\ge 1\%}$ on the **60s or 300s** average for `io.full` or `memory.full` indicates a chronic bottleneck (starvation/deadlock) and demands investigation. `cpu.full` at that level is often just scheduler contention on a busy multi-core system, but is worth watching as it climbs.
* **`some` Stalls (Warning/Actionable):** Sustained values on the **60s or 300s** average are more reliable indicators of system health than momentary spikes:
    * $\mathbf{10\%}$–$\mathbf{25\%}$: Performance degradation is likely. This is often the ideal range to trigger load-shedding or autoscale.
    * $\mathbf{\ge 25\%}$: Performance is severely impacted and the system is likely overloaded.

`psistat` provides calculated 1s, 3s, and 10s averages, which are derived from the kernel's cumulative stall time (the `total=` field in `/proc/pressure/*`, in microseconds). These short-term metrics offer high-resolution visibility into immediate performance bottlenecks that are intentionally smoothed out by the kernel's built-in $60s$ and $300s$ averages.
* Use the **1s average** to spot **transient spikes** (e.g., a short I/O hiccup or lock contention) that cause latency for users.
* Use the **3s and 10s averages** to confirm whether a stall is **momentary** or is becoming a more sustained problem before it affects the long-term averages.

---

## Installation and Use
* Requirements: Linux 4.20+ with PSI enabled (`CONFIG_PSI=y`; `cpu.full` needs 5.13+) and Python 3.11+. Check with `cat /proc/pressure/cpu`.
* Install: `pipx install psistat`
* CLI usage: `psistat -h`
* Typical use: `psistat`.  Its window looks like this:

```
PSIs 18:54:04 | [t]hresh=5% [i]tvl=1s [b]rief=off [d]ump ?:help [q]uit
 ----1s ----3s ---10s ---60s --300s  Full%       ----1s ----3s ---10s ---60s --300s  Some%
   0.00   0.00   0.00   0.00   0.00  cpu            1.70   2.10   6.70   1.10   0.50  cpu
   0.00   0.10   0.20   0.10   0.10  io             0.00   0.20   0.30   0.10   0.10  io
   0.00   0.00   1.40   0.20   0.00  memory         0.00   0.00   1.50   0.20   0.00  memory
──────────────────────────────────────────────────────────────────────────────────────────────
000     8s: 10-18 18:53:56.099  ....................    10.50% cpu.some      >=5% i=1s
001     9s: 10-18 18:53:55.097    14.20% memory.full    14.50% memory.some   >=5% i=1s
002     9s: 10-18 18:53:55.097  ....................    40.70% cpu.some      >=5% i=1s
003    26s: 10-18 18:53:37.995    10.00% io.full        10.50% io.some       >=5% i=1s
004  1m26s: 10-18 18:52:37.665     5.80% io.full         6.00% io.some       >=5% i=1s
005  3m35s: 10-18 18:50:28.977  ....................     5.20% io.some       >=5% i=1s
006  4m35s: 10-18 18:49:28.644  ....................     5.00% io.some       >=5% i=1s
```

* The first line of the screen shows some of the control keys and their current values.
  * `?` shows all the control and navigation keys and the current values (press the bracketed key to change a value).
* The top portion of the screen shows the 1s, 3s, 10s, 60s, and 300s PSI stats (each is the percent stalled during that interval).
  * The 60s and 300s values are averages computed by the kernel.
  * `n/a` means the sample window is not full yet: the 1s–10s columns need a few seconds of samples after startup.
* Below the stats is a list of exception events, newest first. Each line shows:
  * The pressure percentage that met the threshold, for the `full` and/or `some` stat.
  * The event type, plus the threshold and interval in effect when the event was recorded.
* NOTE: The 'full' and 'some' stats are highly correlated, and you often see both in one "event".


## Load Test
To create some test loads, compile and run the `create_load.c` program found at [psi-by-example](https://github.com/shuveb/psi-by-example): `gcc -O2 -o create_load create_load.c && ./create_load`.

