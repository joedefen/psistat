# Linux Pressure Stall Information (PSI) Status App
`psistat` is a python3 program to display the PSIs and to capture/display exception events.  See [PSI - Pressure Stall Information — The Linux Kernel documentation](https://docs.kernel.org/accounting/psi.html) for more information.

`psistat` might be found helpful when encountering unexplained system delays and you wish to identify the general cause.  Regularly occuring high PSIs may indicate the system is undersized or overloaded, and, if warranted, implementing automated load-shedding.  

## Installation
```
  pipx install psistat
```

## Instruction for Use
Typically, simply run `psistat`.  Its window looks like:

```
PSIs 18:54:04 | [tT]hresh=5% [i]tvl=1 [b]rief=off [d]ump ?:help [q]uit
 ---1s ---3s --10s --60s -300s  Full.Stall%      ---1s ---3s --10s --60s -300s  Some.Stall%
   0.0   0.0   0.0   0.0   0.0  cpu.full           1.7   2.1   6.7   1.1   0.5  cpu.some
   0.0   0.1   0.2   0.1   0.1  io.full            0.0   0.2   0.3   0.1   0.1  io.some
   0.0   0.0   1.4   0.2   0.0  memory.full        0.0   0.0   1.5   0.2   0.0  memory.some
──────────────────────────────────────────────────────────────────────────────────────────────
000     8s: 10-18 18:53:56.099  ...................    10.50 cpu.some      >=5 i=1
001     9s: 10-18 18:53:55.097    14.24 memory.full    14.55 memory.some   >=5 i=1
002     9s: 10-18 18:53:55.097  ...................    40.78 cpu.some      >=5 i=1
003    26s: 10-18 18:53:37.995    10.06 io.full        10.51 io.some       >=5 i=1
004  1m26s: 10-18 18:52:37.665     5.86 io.full         6.08 io.some       >=5 i=1
005  3m35s: 10-18 18:50:28.977  ...................     5.28 io.some       >=5 i=1
006  4m35s: 10-18 18:49:28.644  ...................     5.05 io.some       >=5 i=1
```

`psistat` displays:
* The first line of the screen shows some of the control keys and values.
  * `t` decreases the event threshold by 5%; `T` increases it by 5%. Values between 5% and 95% are supported.
  * `i` changes the event interval; if it is 10, then the only 10s average stat is watched for events. 
  * `b` toggles whether the display makes available only as many events as viewable on the screen (no srolling)
    or whether it allows up to 200 events that are scrollable.
  * `d` immediately dumps to the screen all historical events (up to 1000) captured by the running program.
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
    * The pressure value as a percentage relative to the current threshold.
    * The type of event.
  * Since the 'full' and 'some' stats are highly correlated, you will often see both in one "event" as `psistat` collects them.


`psistat` has only a few options:
```

options:
  -h, --help            show this help message and exit
  -t THRESHOLD_PCT, --threshold-pct THRESHOLD_PCT event threshold pct
                      [min=5, max=95, dflt=20]
  -b, --brief           event threshold pct [min=5, max=95, dflt=20]
  -i EVENT_INTERVAL, --event-interval EVENT_INTERVAL event threshold pct
                      [1, 3, 10, 60, 300]
```

## Load Test
To create some test loads, you can use the `create_load.c` program found at
[psi-by-example](https://github.com/shuveb/psi-by-example).

