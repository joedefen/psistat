# Linux Pressure Stall Information (PSI) Status App
`psistat` is a python3 program to display the PSIs and to capture/display exception events. See [PSI - Pressure Stall Information — The Linux Kernel documentation](https://docs.kernel.org/accounting/psi.html) for more information.

## The Unique Value of `psistat`

`psistat` fills a critical gap in Linux monitoring by providing one simple package that offers:

* **High-Granularity, Calculated Averages:** It provides **1s and 3s averages**—data points that are more relevant for real-time latency debugging than the kernel's $60s$/$300s$ averages.
* **Smart Event Logging:** It automatically logs incidents that cross user-defined thresholds ($1\%-99\%$), implements a **cooldown period** to prevent spam, and provides forensic data (sequence number, absolute time, interval used).
* **TUI and Dump Capability:** The ability to instantly **dump the historical log** for copy/paste is a massive feature for quick troubleshooting and reporting that no other simple tool provides.
* **Simplicity:** It's a Python application installed via `pipx`—easy to install, easy to run, and requires zero configuration.

While the raw PSI data exists in the kernel, no tool currently offers the combination of live TUI monitoring, high-resolution calculation, and intelligent event logging that `psistat` does.

---

## Interpreting PSI Values

PSI percentages represent the fraction of time that some or all tasks were stalled waiting for a resource. Since PSIs are workload-dependent, there is no single "bad" value, but these are general guidelines:

* **`full` Stalls (Critical):** Any sustained value $\mathbf{\ge 1\%}$ for `cpu.full`, `io.full`, or `memory.full` on the **60s or 300s** average is a strong indication of a chronic bottleneck (starvation/deadlock) and demands investigation.
* **`some` Stalls (Warning/Actionable):** Sustained values on the **60s or 300s** average are a more reliable indicator of system health than momentary spikes:
    * $\mathbf{10\%-25\%}$: Performance degradation is likely. This is often the ideal range to trigger load-shedding or autoscale.
    * $\mathbf{\ge 25\%}$: Performance is severely impacted and the system is likely overloaded.

`psistat` provides calculated 1s, 3s, and 10s averages, which are derived from the kernel's cumulative stall count. These short-term metrics offer high-resolution visibility into immediate performance bottlenecks that are intentionally smoothed out by the kernel's built-in $60s$ and $300s$ averages. Use the **1s average** to spot **transient spikes** (e.g., a short I/O hiccup or lock contention) that cause latency for users; use the **3s and 10s averages** to confirm if a stall is **momentary** or is becoming a more sustained problem before it affects the long-term averages.

---

## Installation
```
  pipx install psistat
```

## Instruction for Use
Typically, simply run `psistat`.  Its window looks like:

```
PSIs 18:54:04 | [t]hresh=5% [i]tvl=1 [b]rief=off [d]ump ?:help [q]uit
 ---1s ---3s --10s --60s -300s  Full.Stall%      ---1s ---3s --10s --60s -300s  Some.Stall%
   0.0   0.0   0.0   0.0   0.0  cpu.full           1.7   2.1   6.7   1.1   0.5  cpu.some
   0.0   0.1   0.2   0.1   0.1  io.full            0.0   0.2   0.3   0.1   0.1  io.some
   0.0   0.0   1.4   0.2   0.0  memory.full        0.0   0.0   1.5   0.2   0.0  memory.some
──────────────────────────────────────────────────────────────────────────────────────────────
000     8s: 10-18 18:53:56.099  ...................    10.5% cpu.some      >=5% i=1s
001     9s: 10-18 18:53:55.097    14.2% memory.full    14.5% memory.some   >=5% i=1s
002     9s: 10-18 18:53:55.097  ...................    40.7% cpu.some      >=5% i=1s
003    26s: 10-18 18:53:37.995    10.0% io.full        10.5% io.some       >=5% i=1s
004  1m26s: 10-18 18:52:37.665     5.8% io.full         6.0% io.some       >=5% i=1s
005  3m35s: 10-18 18:50:28.977  ...................     5.2% io.some       >=5% i=1s
006  4m35s: 10-18 18:49:28.644  ...................     5.0% io.some       >=5% i=1s
```

`psistat` displays:
* The first line of the screen shows some of the control keys and values.
  * `t` prompts for a new event threshold percent. Values between 1% and 99% are supported.
  * `i` changes the event interval; e.g., if it is 10s, then only the 10s average stat is watched for events. 
  * `b` toggles *brief mode*. When enabled, only events that fit on the screen are shown (disables scrolling). When disabled (Full mode), the full history (up to 200 events) is scrollable.
  * `d` immediately dumps the full event history (up to 1000 events) to the terminal, exits the display mode for easy copy/paste, and prompts you to return when ready.
    A dump will drop out of the display mode so you can copy events to another app, and allow you to display mode return when ready.
  * `?` will show all the control and navagation keys and the current values of the controls.
  * `q` will terminated the app.
* On the top portion of the screen, the 1s, 3s, 10s, 60s, and 300s PSI stats (each is a percent stalled during the interval).
  * The 60s and 300s are averages computed by the system.
* Below the stats is a list of exception events beginning with the most recent;
  each event includes:
  * A sequence number from 000 for the most recent.
  * The relative time and absolute time of the event.
  * For the 'full' and 'some' stats:
    * The pressure value as a percentage that met or exceeded the current threshold.
  * The type of event.
* NOTE: Since the 'full' and 'some' stats are highly correlated, you will often see both in one "event" as `psistat` collects them.


`psistat` has only a few options:
```
usage: psistat [-h] [-b] [-i {1,3,10,60,300}] [-t THRESHOLD_PCT]

options:
  -h, --help            show this help message and exit
  -b, --brief           whether present only as meay events as fit on the screen
  -i {1,3,10,60,300}, --event-interval {1,3,10,60,300}
                        average interval used for events
  -t THRESHOLD_PCT, --threshold-pct THRESHOLD_PCT
                        event threshold percent [1-99,dflt=5]
```

## Load Test
To create some test loads, you can use the `create_load.c` program found at
[psi-by-example](https://github.com/shuveb/psi-by-example).

